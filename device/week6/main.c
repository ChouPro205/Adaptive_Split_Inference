/*
 * Week 6 Device firmware: I1 v2 over I1 BLE binding v1 with diagnostic echo, P1 (I2/1) on
 * the MCU and the NVS nonce reservation (docs/week6_device_edge_plan.md criteria 1-8).
 * USB CDC is control/debug only (binding §1); every radio result comes from BLE.
 * Commands (one per line): HELP, see print_help().
 */
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include <zephyr/device.h>
#include <zephyr/drivers/hwinfo.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/random/random.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/reboot.h>

#include "ble_link.h"
#include "exchange.h"
#include "frag.h"
#include "i1v2_codec.h"
#include "markers.h"
#include "nonce_nvs.h"
#include "packets.h"
#include "quantization.h"
#include "sha256.h"
#include "week6_build.h"
#include "week6_vectors.h"

BUILD_ASSERT(DT_NODE_HAS_COMPAT(DT_CHOSEN(zephyr_console), zephyr_cdc_acm_uart),
             "Week 6 requires USB CDC ACM as control/debug console");
BUILD_ASSERT(W6_VECTOR_COUNT == 50u, "SV3 package has 50 P1 vectors");

#define LINE_MAX 160
#define MAX_ARGS 8
#define POLL_SLICE_MS 50u
#define RESPONSE_BYTES 64u
#define TEST_MODEL_PROFILE_ID 1u /* PUBLIC_TEST_ONLY profile of the 6380 B ceiling (D4) */
#define TEST_SPLIT_ID 1u
#define STRESS_GAP_MS_DEFAULT 3u

static const struct device *const console_device = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));

static uint8_t tx_frame[FRAG_MAX_FRAME];
static uint8_t transformed[PKT_MAX_PAYLOAD];
static uint8_t recovered[PKT_MAX_PAYLOAD];
static float activation[PKT_MAX_PAYLOAD];
static int8_t requantized[PKT_MAX_PAYLOAD];
static uint8_t scale_le[2u * PKT_MAX_CHANNELS];

static const struct exch_config exch_config = EXCH_CONFIG_DEFAULT;
static struct exch_counters counters;
static struct exch exch;
static bool echo_mode = true;
static bool i2_armed;
static bool prov_mode;
static uint32_t last_request_id;
static uint32_t run_number;
static uint32_t boot_reset_cause;
static int s3_vector = -1;
static int s7_vector = -1;

static char line[LINE_MAX];
static unsigned line_length;
static bool line_discard;

/* ------------------------------------------------------------------ console */

static void pace(void)
{
    k_msleep(3);  /* keep the CDC TX FIFO from overflowing on long dumps (week 3/5 lesson) */
}

static void hex_digest(const uint8_t *data, size_t length, char out[65])
{
    uint8_t digest[32];
    sha256(data, length, digest);
    sha256_hex(digest, out);
}

static bool digest_equals(const uint8_t *data, size_t length, const uint8_t expected[32])
{
    uint8_t digest[32];
    sha256(data, length, digest);
    return memcmp(digest, expected, 32) == 0;
}

/* Non-blocking: returns true with a NUL-terminated line when one is complete. */
static bool console_line(void)
{
    unsigned char byte;
    while (uart_poll_in(console_device, &byte) == 0) {
        if (byte == '\n') {
            line[line_length] = '\0';
            const bool ok = !line_discard;
            line_length = 0;
            line_discard = false;
            if (ok) {
                return true;
            }
            printk("ERROR line too long\r\n");
        } else if (byte != '\r' && !line_discard) {
            if (byte == '\0' || line_length + 1U >= sizeof(line)) {
                line_discard = true;
            } else {
                line[line_length++] = (char)byte;
            }
        }
    }
    return false;
}

static void wipe_line(void)
{
    memset(line, 0, sizeof(line));
}

static bool stop_requested(void)
{
    if (console_line()) {
        const bool stop = strcmp(line, "STOP") == 0;
        wipe_line();
        return stop;
    }
    return false;
}

static int split_args(char *text, char *argv[MAX_ARGS])
{
    int argc = 0;
    char *save = NULL;
    for (char *tok = strtok_r(text, " ", &save); tok != NULL && argc < MAX_ARGS;
         tok = strtok_r(NULL, " ", &save)) {
        argv[argc++] = tok;
    }
    return argc;
}

static bool parse_u32(const char *text, uint32_t *out)
{
    char *end = NULL;
    const unsigned long value = strtoul(text, &end, 0);
    if (text[0] == '\0' || end == NULL || *end != '\0') {
        return false;
    }
    *out = (uint32_t)value;
    return true;
}

static int hex_nibble(char c)
{
    if (c >= '0' && c <= '9') {
        return c - '0';
    }
    if (c >= 'a' && c <= 'f') {
        return c - 'a' + 10;
    }
    if (c >= 'A' && c <= 'F') {
        return c - 'A' + 10;
    }
    return -1;
}

static bool parse_hex(const char *text, uint8_t *out, size_t length)
{
    if (strlen(text) != 2u * length) {
        return false;
    }
    for (size_t i = 0; i < length; ++i) {
        const int hi = hex_nibble(text[2u * i]);
        const int lo = hex_nibble(text[2u * i + 1u]);
        if (hi < 0 || lo < 0) {
            return false;
        }
        out[i] = (uint8_t)((hi << 4) | lo);
    }
    return true;
}

static const char *nonce_status_name(enum nonce_status status)
{
    return status == NONCE_READY ? "READY" : status == NONCE_UNPROVISIONED ? "UNPROVISIONED" : "FAULT";
}

/* ------------------------------------------------------------------ status */

#define STATS_MAX_THREADS 16

struct thread_stat {
    const char *name;
    size_t size;
    size_t unused;
};

static struct thread_stat stats[STATS_MAX_THREADS];
static unsigned stats_count;

/* Runs under the scheduler lock: only collect, print afterwards. */
static void collect_thread(const struct k_thread *thread, void *user_data)
{
    ARG_UNUSED(user_data);
    size_t unused = 0;
    if (stats_count >= STATS_MAX_THREADS || k_thread_stack_space_get(thread, &unused) != 0) {
        return;
    }
    const char *name = k_thread_name_get((k_tid_t)thread);
    stats[stats_count++] = (struct thread_stat){
        .name = (name != NULL && name[0] != '\0') ? name : "?",
        .size = thread->stack_info.size,
        .unused = unused,
    };
}

/* High-water marks need CONFIG_INIT_STACKS. */
static void print_stacks(void)
{
    stats_count = 0;
    k_thread_foreach(collect_thread, NULL);
    for (unsigned i = 0; i < stats_count; ++i) {
        printk("STACK %s used=%u size=%u\r\n", stats[i].name,
               (unsigned)(stats[i].size - stats[i].unused), (unsigned)stats[i].size);
    }
}

static void print_link(void)
{
    struct link_info li;
    link_get_info(&li);
    printk("LINK connected=%u ready=%u att_mtu=%u bytes_per_fragment=%u interval_1250us=%u "
           "latency=%u timeout_10ms=%u phy_tx=%u phy_rx=%u data_len_tx=%u data_len_rx=%u "
           "connections=%u disconnections=%u last_reason=0x%02x\r\n",
           li.connected, link_ready(), li.att_mtu, frag_data_bytes(li.att_mtu), li.interval_1250us,
           li.latency, li.timeout_10ms, li.tx_phy, li.rx_phy, li.tx_data_len, li.rx_data_len,
           li.connections, li.disconnections, li.last_disconnect_reason);
}

static void print_nonce(const char *tag)
{
    struct nonce_nvs_info ni;
    char kcv[17];
    nonce_nvs_get_info(&ni);
    for (unsigned i = 0; i < NONCE_KCV_BYTES; ++i) {
        static const char hex[] = "0123456789abcdef";
        kcv[2u * i] = hex[ni.kcv[i] >> 4];
        kcv[2u * i + 1u] = hex[ni.kcv[i] & 0xfu];
    }
    kcv[16] = '\0';
    printk("%s status=%s reason=%s mounted=%u mount_err=%d reserved_through=%llu next=%llu "
           "limit=%llu key_id=%u sender_id=%u key_check=%s writes=%u write_cyc_max=%u "
           "write_cyc_total=%llu\r\n",
           tag, nonce_status_name(ni.status), nonce_reason_names[ni.reason], ni.mounted,
           ni.mount_err, ni.persisted, ni.next, ni.limit, ni.key_id, ni.sender_id,
           ni.status == NONCE_READY ? kcv : "-", ni.writes, ni.write_cycles_max,
           ni.write_cycles_total);
}

static void print_banner(void)
{
    struct nonce_nvs_info ni;
    nonce_nvs_get_info(&ni);
    printk("READY WEEK6 build=%s variant=%s cfg_att_mtu=%d package=%s vectors_manifest=%s "
           "i1v2_vectors=%s\r\n",
           WEEK6_BUILD_ID, WEEK6_VARIANT, MIN(CONFIG_BT_L2CAP_TX_MTU, CONFIG_BT_BUF_ACL_RX_SIZE - 4),
           W6_PACKAGE_ID, W6_PACKAGE_MANIFEST_SHA256, W6_I1V2_VECTORS_SHA256);
    printk("BOOT reset_cause=0x%08x soft_reset=%u boot_in_write=%s\r\n", boot_reset_cause,
           (boot_reset_cause & RESET_SOFTWARE) != 0U,
           ni.boot_noinit_valid ? (ni.boot_in_write ? "1" : "0") : "unknown");
    print_nonce("NONCE");
    print_link();
    printk("CONFIG response_timeout_base_ms=%u per_fragment_budget_ms=%u max_retries=%u "
           "backoff_base_ms=%u reconnect_wait_ms=%u reassembly_timeout_ms=%u tx_credits=%u "
           "tx_credit_timeout_ms=%u max_frame=%u\r\n",
           exch_config.response_timeout_base_ms, exch_config.per_fragment_budget_ms,
           exch_config.max_retries, exch_config.backoff_base_ms, exch_config.reconnect_wait_ms,
           FRAG_REASSEMBLY_TIMEOUT_MS, LINK_TX_CREDITS, LINK_TX_CREDIT_TIMEOUT_MS, FRAG_MAX_FRAME);
}

static void print_help(void)
{
    printk("COMMANDS HELP | STATUS | STACK | MODE ECHO|NORMAL | I2 ARM | REBOOT | DISCONNECT | "
           "CONNPARAM <min> <max>\r\n");
    printk("COMMANDS SELFTEST ENC|P1|QUANT | RUN <count> MIX|PLAIN|SIZES=<a,b,..> | STOP\r\n");
    printk("COMMANDS NONCE | NONCE ALLOC <n> | PROV MODE ON|OFF | PROV KEY <key_id> <sender_id> <hex64> "
           "| PROV ERASE\r\n");
    printk("COMMANDS NTEST STRESS <ms> <reboot 0|1> [gap_ms] | NTEST FAILWRITE | NTEST READBACK | "
           "NTEST BOOT NONE|STATE_CRC|STATE_MISSING|PROVISION_CORRUPT|KEY_MISMATCH | "
           "NTEST SENTINEL WRITE|READ\r\n");
}

/* ------------------------------------------------------------------ tensors */

static struct pkt_tensor vector_tensor(const struct w6_vector *v)
{
    return (struct pkt_tensor){PKT_MODEL_PROFILE_ID, v->split_id, v->channels, v->length, v->q,
                               v->scale_bits};
}

/* D4: 6380 B ceiling frame, PUBLIC_TEST_ONLY shape [1,64,90] carrying real q bytes (s3 vector)
 * and real C=64 scales (s7 vector); echo only, never an Edge inference request. */
static struct pkt_tensor ceiling_tensor(void)
{
    return (struct pkt_tensor){TEST_MODEL_PROFILE_ID, TEST_SPLIT_ID, 64u, 90u,
                               w6_vectors[s3_vector].q, w6_vectors[s7_vector].scale_bits};
}

static void nonce_bytes(uint32_t sender_id, uint64_t sequence, uint8_t nonce[12])
{
    for (unsigned i = 0; i < 4u; ++i) {
        nonce[i] = (uint8_t)(sender_id >> (8u * i));
    }
    for (unsigned i = 0; i < 8u; ++i) {
        nonce[4u + i] = (uint8_t)(sequence >> (8u * i));
    }
}

/* ------------------------------------------------------------------ self tests */

static void selftest_enc(void)
{
    unsigned pass = 0, total = 0;
    for (unsigned g = 0; g < W6_GOLDEN_COUNT; ++g) {
        const struct w6_golden *gv = &w6_goldens[g];
        const struct pkt_tensor t = {gv->model_profile_id, gv->split_id, gv->channels, gv->length,
                                     gv->q, gv->scale_bits};
        uint8_t descriptor[I2_DESCRIPTOR_BYTES];
        uint32_t prot_cycles = 0;
        const uint8_t *payload = (const uint8_t *)gv->q;
        bool ok = true;
        if (gv->nonce != NULL) {
            ok = pkt_descriptor(&t, gv->key_id, descriptor) == I2_OK;
            const uint32_t c0 = link_cycles();
            ok = ok && pkt_protect(&t, gv->key_id, w6_public_key, gv->nonce, descriptor,
                                   transformed, sizeof(transformed)) == I2_OK;
            prot_cycles = link_cycles() - c0;
            payload = transformed;
        }
        const uint32_t c1 = link_cycles();
        const size_t n = ok ? pkt_encode(tx_frame, sizeof(tx_frame), gv->request_id, &t, payload,
                                         gv->nonce != NULL ? descriptor : NULL, gv->nonce)
                            : 0u;
        const uint32_t enc_cycles = link_cycles() - c1;
        char sha[65];
        hex_digest(tx_frame, n, sha);
        const bool match = n == gv->frame_length && digest_equals(tx_frame, n, gv->sha256);
        printk("ENC id=%s len=%u sha256=%s match=%u prot_cyc=%u enc_cyc=%u\r\n", gv->id,
               (unsigned)n, sha, match, prot_cycles, enc_cycles);
        pace();
        pass += match;
        total++;
    }
    for (unsigned r = 0; r < W6_RESPONSE_CASE_COUNT; ++r) {
        const struct w6_response_case *rc = &w6_response_cases[r];
        struct i1v2_response response;
        const int drop = i1v2_parse_response(rc->packet, rc->length, rc->expected_request_id,
                                             FRAG_MAX_FRAME, &response);
        const unsigned kind = drop != 0 ? 0u : (response.status == I1_OK ? 1u : 2u);
        const bool match = kind == rc->expected_kind &&
                           (kind != 2u || response.status == rc->expected_status);
        printk("RESP id=%s result=%s status=%u match=%u\r\n", rc->id,
               kind == 0u ? "DROP" : kind == 1u ? "OK" : "ERROR", kind == 0u ? 0u : response.status,
               match);
        pace();
        pass += match;
        total++;
    }
    printk("ENC END pass=%u total=%u\r\n", pass, total);
}

static void selftest_p1(void)
{
    unsigned pass = 0, with_0x80 = 0;
    for (unsigned i = 0; i < W6_VECTOR_COUNT; ++i) {
        const struct w6_vector *v = &w6_vectors[i];
        const struct pkt_tensor t = vector_tensor(v);
        const size_t count = (size_t)v->channels * v->length;
        uint8_t descriptor[I2_DESCRIPTOR_BYTES], nonce[12];
        nonce_bytes(PKT_SENDER_ID, v->sequence, nonce);
        const bool desc_ok = pkt_descriptor(&t, PKT_KEY_ID, descriptor) == I2_OK &&
                             digest_equals(descriptor, sizeof(descriptor), v->descriptor_sha256);
        uint32_t c0 = link_cycles();
        const int prot = pkt_protect(&t, PKT_KEY_ID, w6_public_key, nonce, descriptor, transformed,
                                     sizeof(transformed));
        const uint32_t prot_cycles = link_cycles() - c0;
        c0 = link_cycles();
        const int unprot = pkt_unprotect(&t, PKT_KEY_ID, w6_public_key, nonce, descriptor,
                                         transformed, recovered, sizeof(recovered));
        const uint32_t unprot_cycles = link_cycles() - c0;
        c0 = link_cycles();
        const size_t n = pkt_encode(tx_frame, sizeof(tx_frame), v->request_id, &t, transformed,
                                    descriptor, nonce);
        const uint32_t enc_cycles = link_cycles() - c0;
        unsigned n80 = 0;
        for (size_t k = 0; k < count; ++k) {
            n80 += transformed[k] == 0x80u;
        }
        char tr_sha[65], req_sha[65];
        c0 = link_cycles();
        hex_digest(transformed, count, tr_sha);
        const uint32_t sha_cycles = link_cycles() - c0;
        hex_digest(tx_frame, n, req_sha);
        const bool tr_match = prot == I2_OK && digest_equals(transformed, count, v->transformed_sha256);
        const bool rt = unprot == I2_OK && memcmp(recovered, v->q, count) == 0;
        const bool req_match = n == v->request_length && digest_equals(tx_frame, n, v->request_sha256);
        const bool ok = desc_ok && tr_match && rt && req_match;
        printk("P1 i=%u s=%u split=%u C=%u L=%u seq=%u tr_sha256=%s tr_match=%u roundtrip=%u "
               "n80=%u req_len=%u req_sha256=%s req_match=%u desc_ok=%u prot_cyc=%u "
               "unprot_cyc=%u enc_cyc=%u sha_cyc=%u\r\n",
               v->index, v->s, v->split_id, v->channels, v->length, v->sequence, tr_sha, tr_match,
               rt, n80, (unsigned)n, req_sha, req_match, desc_ok, prot_cycles, unprot_cycles,
               enc_cycles, sha_cycles);
        pace();
        pass += ok;
        with_0x80 += n80 > 0u;
    }
    printk("P1 END pass=%u total=%u vectors_with_0x80=%u\r\n", pass, W6_VECTOR_COUNT, with_0x80);
}

/* D5: quantize cost on the MCU, input z = q * scale rebuilt with the vector's own shape. */
static void selftest_quant(void)
{
    for (unsigned i = 0; i < W6_VECTOR_COUNT; ++i) {
        const struct w6_vector *v = &w6_vectors[i];
        const size_t count = (size_t)v->channels * v->length;
        for (size_t k = 0; k < count; ++k) {
            float scale;
            memcpy(&scale, &v->scale_bits[k / v->length], sizeof(scale));
            activation[k] = (float)v->q[k] * scale;
        }
        const uint32_t c0 = link_cycles();
        const int status = week5_quantize(activation, count, 1, v->channels, v->length, requantized,
                                          sizeof(requantized), scale_le, sizeof(scale_le));
        const uint32_t cycles = link_cycles() - c0;
        printk("QUANT i=%u s=%u C=%u L=%u status=%d cyc=%u q_equal=%u\r\n", v->index, v->s,
               v->channels, v->length, status, cycles,
               status == 0 && memcmp(requantized, v->q, count) == 0);
        pace();
    }
    printk("QUANT END total=%u\r\n", W6_VECTOR_COUNT);
}

/* ------------------------------------------------------------------ loopback runs */

enum pattern { PATTERN_MIX, PATTERN_PLAIN, PATTERN_SIZES };

struct packet_spec {
    struct pkt_tensor tensor;
    bool i2;
    bool ceiling;
    int s;   /* logical split, -1 for the ceiling frame */
};

static int vector_for_size(uint32_t size, bool *i2)
{
    for (unsigned i = 0; i < W6_VECTOR_COUNT; ++i) {
        const struct w6_vector *v = &w6_vectors[i];
        if (pkt_frame_length(v->channels, v->length, 0) == size) {
            *i2 = false;
            return (int)i;
        }
        if (pkt_frame_length(v->channels, v->length, 1) == size) {
            *i2 = true;
            return (int)i;
        }
    }
    return -1;
}

/* Packet i of a run. MIX (criteria 3-4): vector i % 50, plain in even passes and I2/1 in
 * odd passes, every 25th packet replaced by the 6380 B ceiling frame. */
static bool spec_for(enum pattern pattern, const uint32_t *sizes, unsigned size_count, uint32_t i,
                     struct packet_spec *spec)
{
    spec->ceiling = false;
    if (pattern == PATTERN_SIZES) {
        const uint32_t size = sizes[i % size_count];
        if (size == 6380u) {
            spec->ceiling = true;
        } else {
            bool i2 = false;
            const int v = vector_for_size(size, &i2);
            if (v < 0) {
                return false;
            }
            spec->tensor = vector_tensor(&w6_vectors[v]);
            spec->i2 = i2;
            spec->s = w6_vectors[v].s;
            return true;
        }
    } else if (pattern == PATTERN_MIX && i % 25u == 24u) {
        spec->ceiling = true;
    }
    if (spec->ceiling) {
        spec->tensor = ceiling_tensor();
        spec->i2 = true;
        spec->s = -1;
        return true;
    }
    const struct w6_vector *v = &w6_vectors[i % W6_VECTOR_COUNT];
    spec->tensor = vector_tensor(v);
    spec->i2 = pattern == PATTERN_MIX && ((i / W6_VECTOR_COUNT) % 2u) == 1u;
    spec->s = v->s;
    return true;
}

struct packet_result {
    size_t length;
    uint64_t sequence;
    uint32_t prot_cycles;
    uint32_t enc_cycles;
};

static int build_packet(const struct packet_spec *spec, uint32_t request_id, struct packet_result *r)
{
    const uint8_t *payload = (const uint8_t *)spec->tensor.q;
    uint8_t descriptor[I2_DESCRIPTOR_BYTES], nonce[12];
    r->sequence = 0;
    r->prot_cycles = 0;
    if (spec->i2) {
        const uint8_t *key = nonce_nvs_key();
        if (key == NULL || nonce_nvs_allocate(&r->sequence, nonce) != 0) {
            return -1;   /* nonce §5: persistence fault -> stop sending I2 */
        }
        if (pkt_descriptor(&spec->tensor, PKT_KEY_ID, descriptor) != I2_OK) {
            return -2;
        }
        marker_on(MARKER_PROTECTION);
        const uint32_t c0 = link_cycles();
        const int status = pkt_protect(&spec->tensor, PKT_KEY_ID, key, nonce, descriptor,
                                       transformed, sizeof(transformed));
        r->prot_cycles = link_cycles() - c0;
        marker_off(MARKER_PROTECTION);
        if (status != I2_OK) {
            return -2;
        }
        payload = transformed;
    }
    const uint32_t c1 = link_cycles();
    r->length = pkt_encode(tx_frame, sizeof(tx_frame), request_id, &spec->tensor, payload,
                           spec->i2 ? descriptor : NULL, spec->i2 ? nonce : NULL);
    r->enc_cycles = link_cycles() - c1;
    return r->length == 0u ? -2 : 0;
}

static void print_counters(const char *tag)
{
    const struct exch_counters *c = &counters;
    printk("%s planned=%u sent_first=%u retries=%u timeouts=%u disconnect_abort=%u tx_stall=%u "
           "completed=%u failed=%u error_final=%u edge_busy=%u crc_fail=%u byte_mismatch=%u "
           "duplicate_response=%u stale_response=%u invalid_response=%u wrong_stream=%u\r\n",
           tag, c->planned, c->sent_first, c->retries, c->timeouts, c->disconnect_abort,
           c->tx_stall, c->completed, c->failed, c->error_final, c->edge_busy, c->crc_fail,
           c->byte_mismatch, c->duplicate_response, c->stale_response, c->invalid_response,
           c->wrong_stream);
    uint32_t rc[REASM_COUNTER_COUNT];
    link_rx_counters(rc);
    printk("REASM");
    for (unsigned i = 0; i < REASM_COUNTER_COUNT; ++i) {
        printk(" %s=%u", reasm_counter_names[i], rc[i]);
    }
    printk("\r\n");
}

/* Classifies every reassembled frame against the request in tx_frame[0..sent_length). */
static void drain_frames(uint32_t now, size_t sent_length)
{
    const uint8_t *frame;
    uint16_t length;
    uint8_t stream;
    while (link_rx_take(&frame, &length, &stream)) {
        (void)exch_on_frame(&exch, echo_mode, stream, frame, length, tx_frame, sent_length, now);
        link_rx_release();
    }
}

/* Runs one application packet to completion; returns the TX result of the first attempt. */
static void exchange_packet(size_t length, struct link_tx_result *first, uint32_t *rtt_us)
{
    const uint8_t stream = echo_mode ? FRAG_STREAM_ECHO : FRAG_STREAM_I1;
    struct link_tx_result tx;
    bool have_first = false;
    int64_t send_ticks = 0;
    uint32_t seen_disconnections = link_disconnections();
    memset(first, 0, sizeof(*first));
    exch_begin(&exch, sys_get_le32(tx_frame + 16), k_uptime_get_32());
    for (;;) {
        const uint32_t now = k_uptime_get_32();
        link_rx_tick(now);
        if (link_tx_take_result(&tx)) {
            if (!have_first) {
                *first = tx;
                have_first = true;
            }
            if (tx.status == LINK_TX_DONE) {
                const uint32_t n_resp = echo_mode ? frag_count(length, tx.att_mtu)
                                                  : frag_count(RESPONSE_BYTES, tx.att_mtu);
                exch_sent(&exch, tx.done_ms, n_resp);
            } else {
                exch_send_aborted(&exch, now, tx.status == LINK_TX_STALL);
            }
        }
        drain_frames(now, length);
        const uint32_t disconnections = link_disconnections();
        if (disconnections != seen_disconnections) {
            seen_disconnections = disconnections;
            exch_disconnected(&exch, now);
        }
        uint32_t wait_ms;
        const enum exch_action action = exch_poll(&exch, now, link_ready(), &wait_ms);
        if (action == EXCH_ACT_FINISHED && !link_tx_busy()) {
            break;
        }
        if (action == EXCH_ACT_SEND && !link_tx_busy()) {
            exch_started(&exch, now);
            if (exch.attempts == 1u) {
                send_ticks = k_uptime_ticks();
            }
            if (link_send(tx_frame, (uint16_t)length, stream) != 0) {
                exch_send_aborted(&exch, now, false);
            }
            continue;
        }
        marker_on(MARKER_WAIT);
        (void)k_sem_take(&link_wake, K_MSEC(MIN(wait_ms, POLL_SLICE_MS)));
        marker_off(MARKER_WAIT);
    }
    *rtt_us = exch.state == EXCH_DONE
                  ? (uint32_t)k_ticks_to_us_floor64(k_uptime_ticks() - send_ticks)
                  : 0u;
}

static void run(uint32_t count, enum pattern pattern, const uint32_t *sizes, unsigned size_count,
                const char *pattern_text)
{
    struct packet_spec spec;
    for (uint32_t i = 0; i < count; ++i) {
        if (!spec_for(pattern, sizes, size_count, i, &spec)) {
            printk("ERROR RUN no packet of the requested size\r\n");
            return;
        }
        if (spec.i2 && !i2_armed) {
            printk("ERROR RUN needs I2/1 packets: run the nonce tests (criterion 7), then I2 ARM\r\n");
            return;
        }
    }
    struct link_info li;
    link_get_info(&li);
    memset(&counters, 0, sizeof(counters));
    exch_init(&exch, &exch_config, &counters);
    link_rx_reset_counters();
    link_rx_configure((1U << FRAG_STREAM_I1) | (1U << FRAG_STREAM_ECHO));
    run_number++;
    printk("RUN BEGIN run=%u count=%u pattern=%s mode=%s build=%s variant=%s att_mtu=%u "
           "interval_1250us=%u phy_tx=%u phy_rx=%u\r\n",
           run_number, count, pattern_text, echo_mode ? "ECHO" : "NORMAL", WEEK6_BUILD_ID,
           WEEK6_VARIANT, li.att_mtu, li.interval_1250us, li.tx_phy, li.rx_phy);
    bool aborted = false;
    const char *abort_reason = "";
    for (uint32_t i = 0; i < count; ++i) {
        (void)spec_for(pattern, sizes, size_count, i, &spec);
        const uint32_t request_id = pkt_next_request_id(&last_request_id);
        struct packet_result pr;
        const int built = build_packet(&spec, request_id, &pr);
        if (built != 0) {
            counters.planned++;
            counters.failed++;
            printk("PKT i=%u rid=%08x res=NOT_SENT reason=%s\r\n", i, request_id,
                   built == -1 ? "NONCE_FAULT" : "BUILD");
            aborted = true;
            abort_reason = built == -1 ? "NONCE_FAULT" : "BUILD";
            break;
        }
        struct link_tx_result first;
        uint32_t rtt_us = 0;
        exchange_packet(pr.length, &first, &rtt_us);
        const char *result = exch.state == EXCH_DONE ? "OK" : exch.state == EXCH_ERROR ? "ERROR"
                                                                                     : "FAILED";
        char split[12];
        if (spec.s < 0) {
            strcpy(split, "T");
        } else {
            snprintk(split, sizeof(split), "%d", spec.s);
        }
        printk("PKT i=%u rid=%08x len=%u flags=%u s=%s seq=%llu crc=%08x res=%s att=%u "
               "rtt_us=%u mtu=%u frags=%u tid=%u tx_cyc=%u tx_ms=%u enomem=%u prot_cyc=%u "
               "enc_cyc=%u status=%u\r\n",
               i, request_id, (unsigned)pr.length, spec.i2 ? 2u : 0u, split, pr.sequence,
               sys_get_le32(tx_frame + pr.length - 4u), result, exch.attempts, rtt_us,
               first.att_mtu, first.fragments, first.transfer_id, first.cycles,
               first.done_ms - first.start_ms, first.enomem_retries, pr.prot_cycles,
               pr.enc_cycles, exch.final_status);
        if (stop_requested()) {
            aborted = true;
            abort_reason = "STOP";
            break;
        }
    }
    /* Late frames still count as duplicate/stale responses. */
    k_msleep(200);
    drain_frames(k_uptime_get_32(), 0);
    link_get_info(&li);
    printk("RUN END run=%u requested=%u aborted=%u reason=%s att_mtu=%u interval_1250us=%u "
           "phy_tx=%u phy_rx=%u disconnections=%u\r\n",
           run_number, count, aborted, abort_reason, li.att_mtu, li.interval_1250us, li.tx_phy,
           li.rx_phy, li.disconnections);
    print_counters("COUNTERS");
    print_stacks();
}

static void command_run(int argc, char **argv)
{
    uint32_t count = 0;
    uint32_t sizes[8];
    unsigned size_count = 0;
    enum pattern pattern;
    if (argc != 3 || !parse_u32(argv[1], &count) || count == 0u || count > 100000u) {
        printk("ERROR usage RUN <count> MIX|PLAIN|SIZES=<a,b,..>\r\n");
        return;
    }
    if (strcmp(argv[2], "MIX") == 0) {
        pattern = PATTERN_MIX;
    } else if (strcmp(argv[2], "PLAIN") == 0) {
        pattern = PATTERN_PLAIN;
    } else if (strncmp(argv[2], "SIZES=", 6) == 0) {
        static char list[LINE_MAX];
        strncpy(list, argv[2] + 6, sizeof(list) - 1u);
        char *save = NULL;
        for (char *tok = strtok_r(list, ",", &save); tok != NULL && size_count < 8u;
             tok = strtok_r(NULL, ",", &save)) {
            if (!parse_u32(tok, &sizes[size_count++])) {
                size_count = 0;
                break;
            }
        }
        if (size_count == 0u) {
            printk("ERROR bad SIZES list\r\n");
            return;
        }
        pattern = PATTERN_SIZES;
    } else {
        printk("ERROR unknown pattern\r\n");
        return;
    }
    if (!link_ready()) {
        printk("ERROR link not ready (connect the central and enable notifications)\r\n");
        return;
    }
    run(count, pattern, sizes, size_count, argv[2]);
}

/* ------------------------------------------------------------------ nonce tests */

static void reboot_timer_expired(struct k_timer *timer)
{
    ARG_UNUSED(timer);
    sys_reboot(SYS_REBOOT_COLD);   /* D1: soft reset at an arbitrary point of the stress loop */
}

static K_TIMER_DEFINE(reboot_timer, reboot_timer_expired, NULL);

static void nonce_stress(uint32_t duration_ms, bool reboot, uint32_t gap_ms)
{
    uint8_t nonce[12];
    uint64_t sequence;
    uint32_t iterations = 0;
    printk("NSTRESS BEGIN duration_ms=%u reboot=%u gap_ms=%u\r\n", duration_ms, reboot, gap_ms);
    if (reboot) {
        k_timer_start(&reboot_timer, K_MSEC(duration_ms), K_NO_WAIT);
    }
    const int64_t start = k_uptime_get();
    while (reboot || duration_ms == 0u || k_uptime_get() - start < duration_ms) {
        /* Each iteration reserves a new block, so a Flash write precedes every sequence. */
        nonce_nvs_exhaust_block();
        if (nonce_nvs_allocate(&sequence, nonce) != 0) {
            printk("NSTRESS FAULT\r\n");
            break;
        }
        printk("SEQ %llu\r\n", sequence);   /* printed = used */
        iterations++;
        if (gap_ms > 0u) {
            k_msleep(gap_ms);
        }
        if (stop_requested()) {
            k_timer_stop(&reboot_timer);
            break;
        }
    }
    printk("NSTRESS END iterations=%u\r\n", iterations);
    print_nonce("NONCE");
}

static void nonce_fault_test(const char *name, void (*hook)(void))
{
    struct nonce_nvs_info before, after;
    uint8_t nonce[12];
    uint64_t sequence = 0;
    nonce_nvs_get_info(&before);
    if (before.status != NONCE_READY) {
        printk("NTEST %s result=SKIPPED status=%s\r\n", name, nonce_status_name(before.status));
        return;
    }
    hook();
    nonce_nvs_exhaust_block();
    const int first = nonce_nvs_allocate(&sequence, nonce);
    const int second = nonce_nvs_allocate(&sequence, nonce);
    nonce_nvs_get_info(&after);
    printk("NTEST %s first=%d second=%d status=%s reason=%s writes_before=%u writes_after=%u "
           "result=%s\r\n",
           name, first, second, nonce_status_name(after.status), nonce_reason_names[after.reason],
           before.writes, after.writes,
           first != 0 && second != 0 && after.status == NONCE_FAULT &&
                   after.writes == before.writes + 1u ? "PASS" : "FAIL");
}

static void command_ntest(int argc, char **argv)
{
    uint32_t a = 0, b = 0, gap = STRESS_GAP_MS_DEFAULT;
    if (argc >= 4 && strcmp(argv[1], "STRESS") == 0 && parse_u32(argv[2], &a) &&
        parse_u32(argv[3], &b) && (argc == 4 || parse_u32(argv[4], &gap))) {
        nonce_stress(a, b != 0u, gap);
    } else if (argc == 2 && strcmp(argv[1], "FAILWRITE") == 0) {
        nonce_fault_test("FAILWRITE", nonce_nvs_fail_next_write);
    } else if (argc == 2 && strcmp(argv[1], "READBACK") == 0) {
        nonce_fault_test("READBACK", nonce_nvs_bad_next_readback);
    } else if (argc == 3 && strcmp(argv[1], "BOOT") == 0) {
        static const char *const names[NONCE_HOOK_COUNT] = {
            "NONE", "STATE_CRC", "STATE_MISSING", "PROVISION_CORRUPT", "KEY_MISMATCH"};
        for (int h = 0; h < NONCE_HOOK_COUNT; ++h) {
            if (strcmp(argv[2], names[h]) == 0) {
                const uint32_t writes = nonce_nvs_storage_writes();
                nonce_nvs_reboot_logic((enum nonce_boot_hook)h);
                printk("NTEST BOOT hook=%s storage_writes_during_boot=%u\r\n", names[h],
                       nonce_nvs_storage_writes() - writes);
                print_nonce("NONCE");
                return;
            }
        }
        printk("ERROR unknown BOOT hook\r\n");
    } else if (argc == 3 && strcmp(argv[1], "SENTINEL") == 0) {
        uint8_t value[16];
        char hex[33];
        const int err = strcmp(argv[2], "WRITE") == 0 ? nonce_nvs_sentinel_write(value)
                                                      : nonce_nvs_sentinel_read(value);
        for (unsigned i = 0; i < 16u; ++i) {
            static const char digits[] = "0123456789abcdef";
            hex[2u * i] = err == 0 ? digits[value[i] >> 4] : '-';
            hex[2u * i + 1u] = err == 0 ? digits[value[i] & 0xfu] : '-';
        }
        hex[32] = '\0';
        printk("SENTINEL op=%s err=%d value=%s\r\n", argv[2], err, hex);
        print_nonce("NONCE");
    } else {
        printk("ERROR usage NTEST STRESS <ms> <reboot> [gap] | FAILWRITE | READBACK | BOOT <hook> "
               "| SENTINEL WRITE|READ\r\n");
    }
}

static void command_prov(int argc, char **argv)
{
    if (argc == 3 && strcmp(argv[1], "MODE") == 0) {
        prov_mode = strcmp(argv[2], "ON") == 0;
        printk("PROV MODE=%s (USB CDC only; the key is never echoed)\r\n", prov_mode ? "ON" : "OFF");
        return;
    }
    if (!prov_mode) {
        printk("ERROR PROV MODE ON first\r\n");
        return;
    }
    if (argc == 2 && strcmp(argv[1], "ERASE") == 0) {
        const int err = nonce_nvs_erase_unmountable();
        printk("PROV ERASE err=%d (allowed only when NVS did not mount)\r\n", err);
        print_nonce("NONCE");
        return;
    }
    uint32_t key_id = 0, sender_id = 0;
    uint8_t key[NONCE_KEY_BYTES];
    if (argc == 5 && strcmp(argv[1], "KEY") == 0 && parse_u32(argv[2], &key_id) &&
        parse_u32(argv[3], &sender_id) && parse_hex(argv[4], key, sizeof(key))) {
        memset(argv[4], 0, strlen(argv[4]));
        const enum nonce_prov_result result = nonce_nvs_provision(key_id, sender_id, key);
        uint8_t kcv[NONCE_KCV_BYTES];
        nonce_key_check(key, kcv);
        memset(key, 0, sizeof(key));
        printk("PROV RESULT=%s key_id=%u sender_id=%u key_check=%02x%02x%02x%02x%02x%02x%02x%02x\r\n",
               nonce_prov_names[result], key_id, sender_id, kcv[0], kcv[1], kcv[2], kcv[3], kcv[4],
               kcv[5], kcv[6], kcv[7]);
        print_nonce("NONCE");
        return;
    }
    memset(key, 0, sizeof(key));
    printk("ERROR usage PROV KEY <key_id> <sender_id> <64 hex>\r\n");
}

/* ------------------------------------------------------------------ dispatch */

static void dispatch(void)
{
    char *argv[MAX_ARGS];
    const int argc = split_args(line, argv);
    if (argc == 0) {
        return;
    }
    const char *cmd = argv[0];
    if (strcmp(cmd, "HELP") == 0) {
        print_help();
    } else if (strcmp(cmd, "STATUS") == 0) {
        print_banner();
        printk("STATUS mode=%s i2_armed=%u prov_mode=%u uptime_ms=%lld\r\n",
               echo_mode ? "ECHO" : "NORMAL", i2_armed, prov_mode, k_uptime_get());
    } else if (strcmp(cmd, "STACK") == 0) {
        print_stacks();
    } else if (strcmp(cmd, "MODE") == 0 && argc == 2) {
        echo_mode = strcmp(argv[1], "NORMAL") != 0;
        printk("MODE %s\r\n", echo_mode ? "ECHO" : "NORMAL");
    } else if (strcmp(cmd, "I2") == 0 && argc == 2 && strcmp(argv[1], "ARM") == 0) {
        struct nonce_nvs_info ni;
        nonce_nvs_get_info(&ni);
        i2_armed = ni.status == NONCE_READY;
        printk("I2 ARM=%u status=%s\r\n", i2_armed, nonce_status_name(ni.status));
    } else if (strcmp(cmd, "SELFTEST") == 0 && argc == 2) {
        if (strcmp(argv[1], "ENC") == 0) {
            selftest_enc();
        } else if (strcmp(argv[1], "P1") == 0) {
            selftest_p1();
        } else if (strcmp(argv[1], "QUANT") == 0) {
            selftest_quant();
        } else {
            printk("ERROR SELFTEST ENC|P1|QUANT\r\n");
        }
    } else if (strcmp(cmd, "RUN") == 0) {
        command_run(argc, argv);
    } else if (strcmp(cmd, "NONCE") == 0) {
        uint32_t n = 0;
        if (argc == 3 && strcmp(argv[1], "ALLOC") == 0 && parse_u32(argv[2], &n) && n > 0u) {
            uint64_t first = 0, last = 0, sequence;
            uint8_t nonce[12];
            uint32_t got = 0;
            while (got < n && nonce_nvs_allocate(&sequence, nonce) == 0) {
                first = got == 0u ? sequence : first;
                last = sequence;
                got++;
            }
            printk("NONCE ALLOC requested=%u got=%u first=%llu last=%llu\r\n", n, got, first, last);
        }
        print_nonce("NONCE");
    } else if (strcmp(cmd, "PROV") == 0) {
        command_prov(argc, argv);
    } else if (strcmp(cmd, "NTEST") == 0) {
        command_ntest(argc, argv);
    } else if (strcmp(cmd, "DISCONNECT") == 0) {
        printk("DISCONNECT err=%d\r\n", link_disconnect());
    } else if (strcmp(cmd, "CONNPARAM") == 0 && argc == 3) {
        uint32_t lo = 0, hi = 0;
        if (parse_u32(argv[1], &lo) && parse_u32(argv[2], &hi) && lo >= 6u && lo <= hi && hi <= 3200u) {
            /* Latency 0, supervision timeout 4 s; the result arrives as EVT CONN_PARAM. */
            printk("CONNPARAM request min_1250us=%u max_1250us=%u err=%d\r\n", lo, hi,
                   link_request_conn_params((uint16_t)lo, (uint16_t)hi, 0, 400));
        } else {
            printk("ERROR usage CONNPARAM <min> <max> (units of 1.25 ms, 6..3200)\r\n");
        }
    } else if (strcmp(cmd, "REBOOT") == 0) {
        printk("REBOOT\r\n");
        k_msleep(100);
        sys_reboot(SYS_REBOOT_COLD);
    } else if (strcmp(cmd, "STOP") == 0) {
        printk("STOP (nothing running)\r\n");
    } else {
        printk("ERROR unknown command (HELP)\r\n");
    }
}

int main(void)
{
    if (!device_is_ready(console_device) || markers_init() != 0) {
        return -1;
    }
    struct uart_config config = {
        .baudrate = 115200, .parity = UART_CFG_PARITY_NONE, .stop_bits = UART_CFG_STOP_BITS_1,
        .data_bits = UART_CFG_DATA_BITS_8, .flow_ctrl = UART_CFG_FLOW_CTRL_RTS_CTS,
    };
    if (uart_configure(console_device, &config) != 0) {
        return -1;
    }
    /* Week 3 lesson: arm USB OUT so commands are received. */
    uart_irq_rx_enable(console_device);
    (void)hwinfo_get_reset_cause(&boot_reset_cause);
    (void)hwinfo_clear_reset_cause();
    for (unsigned i = 0; i < W6_VECTOR_COUNT; ++i) {
        if (s3_vector < 0 && w6_vectors[i].s == 3u) {
            s3_vector = (int)i;
        }
        if (s7_vector < 0 && w6_vectors[i].s == 7u) {
            s7_vector = (int)i;
        }
    }
    if (s3_vector < 0 || s7_vector < 0 || w6_vectors[s7_vector].channels != 64u) {
        return -1;
    }
    nonce_nvs_init();
    /* I1 v2 §11: request_id starts at a random non-zero value after every boot. */
    do {
        (void)sys_csrand_get(&last_request_id, sizeof(last_request_id));
    } while (last_request_id == 0u || last_request_id == UINT32_MAX);
    exch_init(&exch, &exch_config, &counters);
    const int bt_err = link_init();
    printk("BOOT bt_enable=%d\r\n", bt_err);
    bool connected_before = false;
    for (;;) {
        uint32_t dtr = 0;
        const bool connected =
            uart_line_ctrl_get(console_device, UART_LINE_CTRL_DTR, &dtr) == 0 && dtr;
        if (connected && !connected_before) {
            k_msleep(100);
            print_banner();
            print_help();
            line_length = 0;
            line_discard = false;
        }
        if (connected && console_line()) {
            dispatch();
            wipe_line();
        }
        connected_before = connected;
        k_msleep(10);
    }
    return 0;
}
