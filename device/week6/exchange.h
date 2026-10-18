/*
 * Device request state machine of I1 BLE binding v1 §6 (timeout, retry, backoff,
 * reconnect wait) and response/echo classification (I1 v2 §8.3, binding §9), with the
 * application-packet counters of binding §11. Portable C, driven by the caller with
 * millisecond timestamps, so the host test can check every timing rule.
 */
#ifndef WEEK6_EXCHANGE_H
#define WEEK6_EXCHANGE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Bench configuration of binding §7 (configuration, not measured performance). */
struct exch_config {
    uint32_t response_timeout_base_ms;
    uint32_t per_fragment_budget_ms;
    uint32_t max_retries;
    uint32_t backoff_base_ms;      /* retry k waits backoff_base_ms * 2^(k-1) */
    uint32_t reconnect_wait_ms;
};

#define EXCH_CONFIG_DEFAULT {8000u, 30u, 2u, 250u, 10000u}

enum exch_state {
    EXCH_IDLE,
    EXCH_SEND,            /* next attempt may start as soon as the link is ready */
    EXCH_SENDING,         /* fragments being handed to the stack */
    EXCH_WAITING,         /* last fragment sent, response timeout running */
    EXCH_RETRY_WAIT,      /* backoff */
    EXCH_RECONNECT_WAIT,  /* attempt due but link down */
    EXCH_DONE,            /* completed: echo matched or valid OK response */
    EXCH_ERROR,           /* final ERROR_RESPONSE other than EDGE_BUSY */
    EXCH_FAILED           /* retries exhausted or reconnect wait expired */
};

enum exch_action { EXCH_ACT_SEND, EXCH_ACT_WAIT, EXCH_ACT_FINISHED };

enum exch_rx_kind { EXCH_RX_DROPPED, EXCH_RX_MATCH, EXCH_RX_EDGE_BUSY, EXCH_RX_ERROR_FINAL };

/* Binding §11, per application packet. */
struct exch_counters {
    uint32_t planned;
    uint32_t sent_first;
    uint32_t retries;
    uint32_t timeouts;
    uint32_t disconnect_abort;
    uint32_t tx_stall;
    uint32_t completed;
    uint32_t failed;
    uint32_t error_final;
    uint32_t edge_busy;
    uint32_t crc_fail;
    uint32_t byte_mismatch;
    uint32_t duplicate_response;
    uint32_t stale_response;
    uint32_t invalid_response;
    uint32_t wrong_stream;
};

struct exch {
    struct exch_config cfg;
    struct exch_counters *counters;
    enum exch_state state;
    uint32_t attempts;           /* transmissions started for this request */
    uint32_t deadline_ms;
    uint32_t timeout_ms;         /* T of the attempt in WAITING */
    uint32_t first_send_ms;
    uint32_t last_send_ms;
    uint32_t finished_ms;
    uint32_t request_id;
    uint32_t last_finished_id;   /* request_id of the previous request (duplicate detection) */
    uint16_t final_status;       /* I1 status of a final response */
    float logits[5];
};

void exch_init(struct exch *x, const struct exch_config *cfg, struct exch_counters *counters);
/* Starts a new application packet; counts it in planned. */
void exch_begin(struct exch *x, uint32_t request_id, uint32_t now_ms);
/* What to do now; *wait_ms is the longest the caller may sleep before polling again. */
enum exch_action exch_poll(struct exch *x, uint32_t now_ms, bool link_ready, uint32_t *wait_ms);
/* Caller started transmitting the frame (after EXCH_ACT_SEND). */
void exch_started(struct exch *x, uint32_t now_ms);
/* Completion callback of the last fragment; n_resp = expected response fragments. */
void exch_sent(struct exch *x, uint32_t now_ms, uint32_t n_resp);
/* The binding aborted the transfer: credit timeout (stall) or connection loss. */
void exch_send_aborted(struct exch *x, uint32_t now_ms, bool stall);
void exch_disconnected(struct exch *x, uint32_t now_ms);
bool exch_finished(const struct exch *x);
uint32_t exch_response_timeout_ms(const struct exch_config *cfg, uint32_t n_resp);
uint32_t exch_backoff_ms(const struct exch_config *cfg, uint32_t retry_index);

/*
 * Classifies a reassembled frame and updates counters and state. echo_mode selects
 * binding §9 (byte-exact echo on stream 0x02) or I1 v2 §8.3 responses on stream 0x01.
 * sent/sent_length is the frame of the request in flight.
 */
enum exch_rx_kind exch_on_frame(struct exch *x, bool echo_mode, uint8_t stream,
                                const uint8_t *frame, size_t length, const uint8_t *sent,
                                size_t sent_length, uint32_t now_ms);

#endif
