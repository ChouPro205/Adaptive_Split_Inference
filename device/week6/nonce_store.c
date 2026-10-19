/* See nonce_store.h. Decision order mirrors contracts/i1v2_ref/nonce_reservation.py. */
#include "nonce_store.h"

#include <string.h>

#include "i1v2_codec.h"
#include "i2_reference.h"

const char *const nonce_reason_names[NONCE_R_COUNT] = {
    "NONE", "MOUNT", "READ_ERROR", "PROVISION_CORRUPT", "STATE_MISSING", "STATE_CRC",
    "STATE_FORMAT", "STATE_KEY_MISMATCH", "NOT_IN_REGISTRY", "WRITE_FAILED", "WRITE_ZERO",
    "READBACK", "EXHAUSTED",
};

const char *const nonce_prov_names[NONCE_PROV_COUNT] = {
    "OK", "NOT_IN_REGISTRY", "STATE_IN_USE", "STATE_UNREADABLE", "WRITE_FAILED", "READBACK",
};

#define RECORD_VERSION 1u
#define READ_BUFFER 64u

static uint32_t get32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

static uint64_t get64(const uint8_t *p)
{
    return (uint64_t)get32(p) | ((uint64_t)get32(p + 4) << 32);
}

static void put32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

static void put64(uint8_t *p, uint64_t v)
{
    put32(p, (uint32_t)v);
    put32(p + 4, (uint32_t)(v >> 32));
}

void nonce_key_check(const uint8_t key[NONCE_KEY_BYTES], uint8_t out[NONCE_KCV_BYTES])
{
    static const uint8_t zero_nonce[12];
    uint8_t block[64];

    i2_chacha20_block(key, 0u, zero_nonce, block);
    memcpy(out, block, NONCE_KCV_BYTES);
    memset(block, 0, sizeof(block));
}

static void header(uint8_t *out, const char magic[4], uint32_t key_id, uint32_t sender_id)
{
    memcpy(out, magic, 4);
    out[4] = RECORD_VERSION;
    out[5] = out[6] = out[7] = 0u;
    put32(out + 8, key_id);
    put32(out + 12, sender_id);
}

void nonce_encode_state(uint8_t out[NONCE_STATE_BYTES], uint32_t key_id, uint32_t sender_id,
                        uint64_t reserved_through, const uint8_t kcv[NONCE_KCV_BYTES])
{
    header(out, "I2NS", key_id, sender_id);
    put64(out + 16, reserved_through);
    memcpy(out + 24, kcv, NONCE_KCV_BYTES);
    put32(out + 32, i1v2_crc32(out, 32));
}

void nonce_encode_provision(uint8_t out[NONCE_PROVISION_BYTES], uint32_t key_id,
                            uint32_t sender_id, const uint8_t key[NONCE_KEY_BYTES])
{
    header(out, "I2KY", key_id, sender_id);
    memcpy(out + 16, key, NONCE_KEY_BYTES);
    put32(out + 48, i1v2_crc32(out, 48));
}

static bool header_ok(const uint8_t *record, const char magic[4])
{
    return memcmp(record, magic, 4) == 0 && record[4] == RECORD_VERSION && record[5] == 0u &&
           record[6] == 0u && record[7] == 0u;
}

enum nonce_reason nonce_decode_state(const uint8_t *record, int length, uint32_t *key_id,
                                     uint32_t *sender_id, uint64_t *reserved_through,
                                     uint8_t kcv[NONCE_KCV_BYTES])
{
    if (record == NULL || length != (int)NONCE_STATE_BYTES) {
        return NONCE_R_STATE_MISSING;
    }
    if (get32(record + 32) != i1v2_crc32(record, 32)) {
        return NONCE_R_STATE_CRC;
    }
    if (!header_ok(record, "I2NS")) {
        return NONCE_R_STATE_FORMAT;
    }
    *key_id = get32(record + 8);
    *sender_id = get32(record + 12);
    *reserved_through = get64(record + 16);
    memcpy(kcv, record + 24, NONCE_KCV_BYTES);
    return NONCE_R_NONE;
}

static enum nonce_reason decode_provision(const uint8_t *record, int length, uint32_t *key_id,
                                          uint32_t *sender_id, uint8_t key[NONCE_KEY_BYTES])
{
    if (length != (int)NONCE_PROVISION_BYTES || get32(record + 48) != i1v2_crc32(record, 48) ||
        !header_ok(record, "I2KY")) {
        return NONCE_R_PROVISION_CORRUPT;
    }
    *key_id = get32(record + 8);
    *sender_id = get32(record + 12);
    memcpy(key, record + 16, NONCE_KEY_BYTES);
    return NONCE_R_NONE;
}

static void set_fault(struct nonce_alloc *a, enum nonce_reason reason)
{
    a->status = NONCE_FAULT;
    a->reason = reason;
}

void nonce_boot(struct nonce_alloc *a, const struct nonce_storage *storage, bool mounted,
                const struct nonce_scope *scope, uint64_t block)
{
    uint8_t record[READ_BUFFER];
    uint32_t key_id, sender_id, s_key_id, s_sender_id;
    uint64_t reserved_through;
    uint8_t kcv[NONCE_KCV_BYTES], expected_kcv[NONCE_KCV_BYTES];

    memset(a, 0, sizeof(*a));
    a->storage = storage;
    a->block = block;
    if (!mounted) {
        set_fault(a, NONCE_R_MOUNT);
        return;
    }
    int n = storage->read(storage->ctx, NONCE_ID_PROVISION, record, sizeof(record));
    if (n == NONCE_ERR_NOT_FOUND) {
        a->status = NONCE_UNPROVISIONED;
        a->reason = NONCE_R_NONE;
        return;
    }
    if (n < 0) {
        set_fault(a, NONCE_R_READ_ERROR);
        return;
    }
    enum nonce_reason reason = decode_provision(record, n, &key_id, &sender_id, a->key);
    if (reason != NONCE_R_NONE) {
        set_fault(a, reason);
        return;
    }
    n = storage->read(storage->ctx, NONCE_ID_STATE, record, sizeof(record));
    if (n < 0 && n != NONCE_ERR_NOT_FOUND) {
        set_fault(a, NONCE_R_READ_ERROR);
        return;
    }
    reason = nonce_decode_state(n < 0 ? NULL : record, n, &s_key_id, &s_sender_id,
                                &reserved_through, kcv);
    if (reason != NONCE_R_NONE) {
        set_fault(a, reason);
        return;
    }
    nonce_key_check(a->key, expected_kcv);
    if (s_key_id != key_id || s_sender_id != sender_id ||
        memcmp(kcv, expected_kcv, NONCE_KCV_BYTES) != 0) {
        set_fault(a, NONCE_R_STATE_KEY_MISMATCH);
        return;
    }
    if (key_id != scope->key_id || sender_id != scope->sender_id) {
        set_fault(a, NONCE_R_NOT_IN_REGISTRY);
        return;
    }
    a->status = NONCE_READY;
    a->key_id = key_id;
    a->sender_id = sender_id;
    memcpy(a->kcv, kcv, NONCE_KCV_BYTES);
    a->persisted = reserved_through;
    a->next = reserved_through + 1u; /* everything <= reserved_through may have been used */
    a->limit = reserved_through;     /* nothing reserved in this boot yet */
}

static int reserve(struct nonce_alloc *a)
{
    uint8_t record[NONCE_STATE_BYTES], readback[READ_BUFFER];

    if (a->persisted > UINT64_MAX - a->block) {
        set_fault(a, NONCE_R_EXHAUSTED);
        return -1;
    }
    const uint64_t new_limit = a->persisted + a->block;
    nonce_encode_state(record, a->key_id, a->sender_id, new_limit, a->kcv);
    a->writes++;
    const int written = a->storage->write(a->storage->ctx, NONCE_ID_STATE, record, sizeof(record));
    if (written < 0) {
        set_fault(a, NONCE_R_WRITE_FAILED);
        return -1;
    }
    if (written == 0) {
        /* The value always grows, so "nothing written" means the store is not behaving. */
        set_fault(a, NONCE_R_WRITE_ZERO);
        return -1;
    }
    const int n = a->storage->read(a->storage->ctx, NONCE_ID_STATE, readback, sizeof(readback));
    if (n != (int)sizeof(record) || memcmp(readback, record, sizeof(record)) != 0) {
        set_fault(a, NONCE_R_READBACK);
        return -1;
    }
    a->persisted = a->limit = new_limit;
    return 0;
}

int nonce_allocate(struct nonce_alloc *a, uint64_t *sequence)
{
    if (a->status != NONCE_READY) {
        return -1;
    }
    if (a->next > a->limit && reserve(a) != 0) {
        return -1;
    }
    *sequence = a->next++;
    return 0;
}

void nonce_make(const struct nonce_alloc *a, uint64_t sequence, uint8_t nonce[12])
{
    put32(nonce, a->sender_id);
    put64(nonce + 4, sequence);
}

enum nonce_prov_result nonce_provision(const struct nonce_storage *storage,
                                       const struct nonce_scope *scope, uint32_t key_id,
                                       uint32_t sender_id, const uint8_t key[NONCE_KEY_BYTES])
{
    uint8_t state[NONCE_STATE_BYTES], provision[NONCE_PROVISION_BYTES], record[READ_BUFFER];
    uint8_t kcv[NONCE_KCV_BYTES], old_kcv[NONCE_KCV_BYTES];
    uint32_t s_key_id, s_sender_id;
    uint64_t reserved_through;

    if (key_id != scope->key_id || sender_id != scope->sender_id) {
        return NONCE_PROV_NOT_IN_REGISTRY;
    }
    int n = storage->read(storage->ctx, NONCE_ID_STATE, record, sizeof(record));
    const bool state_absent = n == NONCE_ERR_NOT_FOUND;
    if (!state_absent) {
        if (n < 0 || nonce_decode_state(record, n, &s_key_id, &s_sender_id, &reserved_through,
                                        old_kcv) != NONCE_R_NONE ||
            s_key_id != key_id || s_sender_id != sender_id) {
            return NONCE_PROV_STATE_UNREADABLE;
        }
        if (reserved_through != 0u) {
            return NONCE_PROV_STATE_IN_USE;
        }
    }
    n = storage->read(storage->ctx, NONCE_ID_PROVISION, record, sizeof(record));
    if (n != NONCE_ERR_NOT_FOUND && (n < 0 || state_absent)) {
        /* A key record without its state means the state was lost: §4 step 7. */
        return NONCE_PROV_STATE_UNREADABLE;
    }
    nonce_key_check(key, kcv);
    nonce_encode_state(state, key_id, sender_id, 0u, kcv);
    nonce_encode_provision(provision, key_id, sender_id, key);
    /* 0 = identical record already stored (repeat after power loss in step 5). */
    if (storage->write(storage->ctx, NONCE_ID_STATE, state, sizeof(state)) < 0 ||
        storage->write(storage->ctx, NONCE_ID_PROVISION, provision, sizeof(provision)) < 0) {
        memset(provision, 0, sizeof(provision));
        return NONCE_PROV_WRITE_FAILED;
    }
    enum nonce_prov_result result = NONCE_PROV_OK;
    n = storage->read(storage->ctx, NONCE_ID_STATE, record, sizeof(record));
    if (n != (int)sizeof(state) || memcmp(record, state, sizeof(state)) != 0) {
        result = NONCE_PROV_READBACK;
    }
    n = storage->read(storage->ctx, NONCE_ID_PROVISION, record, sizeof(record));
    if (n != (int)sizeof(provision) || memcmp(record, provision, sizeof(provision)) != 0) {
        result = NONCE_PROV_READBACK;
    }
    memset(provision, 0, sizeof(provision));
    memset(record, 0, sizeof(record));
    return result;
}
