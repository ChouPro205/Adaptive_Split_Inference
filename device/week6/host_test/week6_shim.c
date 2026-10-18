/*
 * Host-only flat C API over the portable week 6 modules for device/scripts/test_week6_host.py
 * (ctypes). Never linked into the firmware. The in-memory store models NVS records that are
 * written atomically, plus fault injection for power loss and write failures.
 */
#include <errno.h>
#include <stdint.h>
#include <string.h>

#include "exchange.h"
#include "frag.h"
#include "nonce_store.h"
#include "packets.h"
#include "sha256.h"

#ifdef _WIN32
#define API __declspec(dllexport)
#else
#define API
#endif

/* ---------------- reassembly ---------------- */
static uint8_t reasm_buffer[FRAG_MAX_FRAME];
static struct reasm reasm;
static int reasm_hold;

API void shim_reasm_init(uint16_t capacity, uint8_t stream_mask, uint32_t timeout_ms, int hold)
{
    reasm_init(&reasm, reasm_buffer, capacity, stream_mask, timeout_ms);
    reasm_hold = hold;
}

/* 1 and the frame when one completes (released at once unless hold). */
API int shim_reasm_feed(const uint8_t *data, uint16_t length, uint32_t now_ms, uint8_t *frame,
                        uint16_t *frame_length, uint8_t *stream)
{
    if (!reasm_feed(&reasm, data, length, now_ms)) {
        return 0;
    }
    memcpy(frame, reasm.buffer, reasm.pending_length);
    *frame_length = reasm.pending_length;
    *stream = reasm.pending_stream;
    if (!reasm_hold) {
        reasm_release(&reasm);
    }
    return 1;
}

API void shim_reasm_tick(uint32_t now_ms) { reasm_tick(&reasm, now_ms); }
API void shim_reasm_disconnect(void) { reasm_disconnect(&reasm); }
API void shim_reasm_release(void) { reasm_release(&reasm); }

API void shim_reasm_counters(uint32_t out[REASM_COUNTER_COUNT])
{
    memcpy(out, reasm.counters, sizeof(reasm.counters));
}

API const char *shim_reasm_counter_name(int index) { return reasm_counter_names[index]; }
API uint16_t shim_frag_data_bytes(uint16_t mtu) { return frag_data_bytes(mtu); }
API uint32_t shim_frag_count(uint32_t length, uint16_t mtu) { return frag_count(length, mtu); }

API void shim_frag_header(uint8_t out[8], uint8_t stream, uint16_t transfer_id, uint16_t offset,
                          uint16_t total)
{
    frag_write_header(out, stream, transfer_id, offset, total);
}

API uint16_t shim_next_transfer_id(uint16_t *last) { return frag_next_transfer_id(last); }

/* ---------------- exchange ---------------- */
static struct exch exch;
static struct exch_counters exch_counters;

API void shim_exch_init(uint32_t base, uint32_t per_fragment, uint32_t retries, uint32_t backoff,
                        uint32_t reconnect)
{
    const struct exch_config cfg = {base, per_fragment, retries, backoff, reconnect};
    memset(&exch_counters, 0, sizeof(exch_counters));
    exch_init(&exch, &cfg, &exch_counters);
}

API void shim_exch_begin(uint32_t request_id, uint32_t now) { exch_begin(&exch, request_id, now); }

API int shim_exch_poll(uint32_t now, int ready, uint32_t *wait_ms)
{
    return (int)exch_poll(&exch, now, ready != 0, wait_ms);
}

API void shim_exch_started(uint32_t now) { exch_started(&exch, now); }
API void shim_exch_sent(uint32_t now, uint32_t n_resp) { exch_sent(&exch, now, n_resp); }
API void shim_exch_aborted(uint32_t now, int stall) { exch_send_aborted(&exch, now, stall != 0); }
API void shim_exch_disconnected(uint32_t now) { exch_disconnected(&exch, now); }
API int shim_exch_state(void) { return (int)exch.state; }
API uint32_t shim_exch_attempts(void) { return exch.attempts; }
API uint16_t shim_exch_status(void) { return exch.final_status; }
API uint32_t shim_exch_timeout(void) { return exch.timeout_ms; }

API int shim_exch_frame(int echo, uint8_t stream, const uint8_t *frame, uint32_t length,
                        const uint8_t *sent, uint32_t sent_length, uint32_t now)
{
    return (int)exch_on_frame(&exch, echo != 0, stream, frame, length, sent, sent_length, now);
}

API void shim_exch_counters(uint32_t out[16])
{
    memcpy(out, &exch_counters, sizeof(exch_counters));
}

/* ---------------- nonce store ---------------- */
enum fault { F_NONE, F_FAIL_WRITE, F_CRASH_BEFORE, F_CRASH_AFTER, F_WRITE_ZERO, F_BAD_READBACK };

#define SLOTS 4
static struct {
    uint16_t id;
    int length; /* -1 = empty */
    uint8_t data[64];
} slots[SLOTS];
static int fault_mode;
static int crashed;
static int corrupt_reads;
static uint32_t store_writes;

static int find(uint16_t id)
{
    for (int i = 0; i < SLOTS; ++i) {
        if (slots[i].length >= 0 && slots[i].id == id) {
            return i;
        }
    }
    return -1;
}

static int store_read(void *ctx, uint16_t id, uint8_t *buffer, size_t length)
{
    (void)ctx;
    const int i = find(id);
    if (i < 0) {
        return NONCE_ERR_NOT_FOUND;
    }
    const size_t n = (size_t)slots[i].length < length ? (size_t)slots[i].length : length;
    memcpy(buffer, slots[i].data, n);
    if (corrupt_reads > 0 && n > 0) {
        corrupt_reads--;
        buffer[n - 1] ^= 0x01u;
    }
    return slots[i].length;
}

static void commit(uint16_t id, const uint8_t *data, size_t length)
{
    int i = find(id);
    if (i < 0) {
        for (i = 0; i < SLOTS && slots[i].length >= 0; ++i) {
        }
    }
    slots[i].id = id;
    slots[i].length = (int)length;
    memcpy(slots[i].data, data, length);
}

static int store_write(void *ctx, uint16_t id, const uint8_t *data, size_t length)
{
    (void)ctx;
    if (crashed) {
        return -EIO; /* power is gone: nothing after the crash lands */
    }
    store_writes++;
    const int mode = fault_mode;
    fault_mode = F_NONE;
    switch (mode) {
    case F_FAIL_WRITE:
        return -EIO;
    case F_CRASH_BEFORE:
        crashed = 1;
        return -EIO;
    case F_CRASH_AFTER:
        commit(id, data, length);
        crashed = 1;
        return (int)length;
    case F_WRITE_ZERO:
        return 0;
    case F_BAD_READBACK:
        commit(id, data, length);
        corrupt_reads = 1;
        return (int)length;
    default:
        commit(id, data, length);
        return (int)length;
    }
}

static const struct nonce_storage storage = {store_read, store_write, NULL};
static const struct nonce_scope scope = {PKT_KEY_ID, PKT_SENDER_ID};
static struct nonce_alloc alloc;

API void shim_store_reset(void)
{
    for (int i = 0; i < SLOTS; ++i) {
        slots[i].length = -1;
    }
    fault_mode = F_NONE;
    crashed = 0;
    corrupt_reads = 0;
    store_writes = 0;
}

API void shim_store_fault(int mode) { fault_mode = mode; }
API int shim_store_crashed(void) { return crashed; }
API uint32_t shim_store_writes(void) { return store_writes; }

API int shim_store_get(uint16_t id, uint8_t *out, int capacity)
{
    const int i = find(id);
    if (i < 0) {
        return NONCE_ERR_NOT_FOUND;
    }
    memcpy(out, slots[i].data, (size_t)(slots[i].length < capacity ? slots[i].length : capacity));
    return slots[i].length;
}

API void shim_store_put(uint16_t id, const uint8_t *data, int length) { commit(id, data, (size_t)length); }

API void shim_store_delete(uint16_t id)
{
    const int i = find(id);
    if (i >= 0) {
        slots[i].length = -1;
    }
}

/* Reboot: RAM state is lost, committed records survive. */
API int shim_nonce_boot(int mounted, uint64_t block)
{
    crashed = 0;
    corrupt_reads = 0;
    nonce_boot(&alloc, &storage, mounted != 0, &scope, block);
    return (int)alloc.status;
}

API int shim_nonce_reason(void) { return (int)alloc.reason; }
API const char *shim_nonce_reason_name(int reason) { return nonce_reason_names[reason]; }
API int shim_nonce_allocate(uint64_t *sequence) { return nonce_allocate(&alloc, sequence); }
API uint32_t shim_nonce_writes(void) { return alloc.writes; }

API void shim_nonce_numbers(uint64_t out[3])
{
    out[0] = alloc.persisted;
    out[1] = alloc.next;
    out[2] = alloc.limit;
}

API int shim_nonce_provision(uint32_t key_id, uint32_t sender_id, const uint8_t *key)
{
    return (int)nonce_provision(&storage, &scope, key_id, sender_id, key);
}

API void shim_key_check(const uint8_t *key, uint8_t *out) { nonce_key_check(key, out); }

API void shim_encode_state(uint8_t *out, uint32_t key_id, uint32_t sender_id, uint64_t reserved,
                           const uint8_t *kcv)
{
    nonce_encode_state(out, key_id, sender_id, reserved, kcv);
}

API void shim_encode_provision(uint8_t *out, uint32_t key_id, uint32_t sender_id,
                               const uint8_t *key)
{
    nonce_encode_provision(out, key_id, sender_id, key);
}

/* ---------------- packets / sha ---------------- */
API uint32_t shim_build(uint8_t *out, uint32_t capacity, uint32_t request_id, uint32_t model,
                        uint16_t split_id, uint16_t channels, uint32_t length, const int8_t *q,
                        const uint32_t *scale_bits, const uint8_t *key, uint32_t key_id,
                        const uint8_t *nonce, uint8_t *transformed, uint8_t *recovered)
{
    const struct pkt_tensor t = {model, split_id, channels, length, q, scale_bits};
    uint8_t descriptor[I2_DESCRIPTOR_BYTES];
    if (key == NULL) {
        return (uint32_t)pkt_encode(out, capacity, request_id, &t, (const uint8_t *)q, NULL, NULL);
    }
    if (pkt_descriptor(&t, key_id, descriptor) != I2_OK ||
        pkt_protect(&t, key_id, key, nonce, descriptor, transformed, PKT_MAX_PAYLOAD) != I2_OK ||
        pkt_unprotect(&t, key_id, key, nonce, descriptor, transformed, recovered,
                      PKT_MAX_PAYLOAD) != I2_OK) {
        return 0;
    }
    return (uint32_t)pkt_encode(out, capacity, request_id, &t, transformed, descriptor, nonce);
}

API uint32_t shim_frame_length(uint16_t channels, uint32_t length, int transformed)
{
    return pkt_frame_length(channels, length, transformed);
}

API uint32_t shim_next_request_id(uint32_t *last) { return pkt_next_request_id(last); }

API void shim_sha256(const uint8_t *data, uint32_t length, uint8_t *digest)
{
    sha256(data, length, digest);
}
