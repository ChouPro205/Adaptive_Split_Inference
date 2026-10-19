/* See exchange.h. Rules: contracts/i1_ble_binding_v1.md §6, §9, §11; I1 v2 §8.3. */
#include "exchange.h"

#include <string.h>

#include "frag.h"
#include "i1v2_codec.h"

static uint32_t get32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

/* Wrap-safe "now has reached deadline" for a 32-bit millisecond clock. */
static bool due(uint32_t now_ms, uint32_t deadline_ms)
{
    return (int32_t)(now_ms - deadline_ms) >= 0;
}

uint32_t exch_response_timeout_ms(const struct exch_config *cfg, uint32_t n_resp)
{
    return cfg->response_timeout_base_ms + n_resp * cfg->per_fragment_budget_ms;
}

uint32_t exch_backoff_ms(const struct exch_config *cfg, uint32_t retry_index)
{
    return retry_index == 0u ? 0u : cfg->backoff_base_ms << (retry_index - 1u);
}

void exch_init(struct exch *x, const struct exch_config *cfg, struct exch_counters *counters)
{
    memset(x, 0, sizeof(*x));
    x->cfg = *cfg;
    x->counters = counters;
    x->state = EXCH_IDLE;
}

bool exch_finished(const struct exch *x)
{
    return x->state == EXCH_IDLE || x->state == EXCH_DONE || x->state == EXCH_ERROR ||
           x->state == EXCH_FAILED;
}

static void finish(struct exch *x, enum exch_state state, uint32_t now_ms)
{
    x->state = state;
    x->finished_ms = now_ms;
}

void exch_begin(struct exch *x, uint32_t request_id, uint32_t now_ms)
{
    if (x->request_id != 0u) {
        x->last_finished_id = x->request_id;
    }
    x->request_id = request_id;
    x->state = EXCH_SEND;
    x->attempts = 0;
    x->deadline_ms = now_ms;
    x->timeout_ms = 0;
    x->first_send_ms = 0;
    x->last_send_ms = 0;
    x->finished_ms = 0;
    x->final_status = 0;
    memset(x->logits, 0, sizeof(x->logits));
    x->counters->planned++;
}

/* One attempt failed (timeout, stall, disconnect, EDGE_BUSY): back off or give up. */
static void attempt_failed(struct exch *x, uint32_t now_ms)
{
    if (x->attempts > x->cfg.max_retries) {
        x->counters->failed++;
        finish(x, EXCH_FAILED, now_ms);
        return;
    }
    x->state = EXCH_RETRY_WAIT;
    x->deadline_ms = now_ms + exch_backoff_ms(&x->cfg, x->attempts);
}

enum exch_action exch_poll(struct exch *x, uint32_t now_ms, bool link_ready, uint32_t *wait_ms)
{
    *wait_ms = 0;
    for (;;) {
        switch (x->state) {
        case EXCH_SEND:
            if (link_ready) {
                return EXCH_ACT_SEND;
            }
            x->state = EXCH_RECONNECT_WAIT;
            x->deadline_ms = now_ms + x->cfg.reconnect_wait_ms;
            continue;
        case EXCH_RECONNECT_WAIT:
            if (link_ready) {
                x->state = EXCH_SEND;
                return EXCH_ACT_SEND;
            }
            if (due(now_ms, x->deadline_ms)) {
                x->counters->failed++;
                finish(x, EXCH_FAILED, now_ms);
                return EXCH_ACT_FINISHED;
            }
            *wait_ms = x->deadline_ms - now_ms;
            return EXCH_ACT_WAIT;
        case EXCH_SENDING:
            /* The binding always reports completion or abort (credit timeout). */
            *wait_ms = UINT32_MAX;
            return EXCH_ACT_WAIT;
        case EXCH_WAITING:
            if (due(now_ms, x->deadline_ms)) {
                x->counters->timeouts++;
                attempt_failed(x, now_ms);
                continue;
            }
            *wait_ms = x->deadline_ms - now_ms;
            return EXCH_ACT_WAIT;
        case EXCH_RETRY_WAIT:
            if (due(now_ms, x->deadline_ms)) {
                x->state = EXCH_SEND;
                continue;
            }
            *wait_ms = x->deadline_ms - now_ms;
            return EXCH_ACT_WAIT;
        case EXCH_IDLE:
        case EXCH_DONE:
        case EXCH_ERROR:
        case EXCH_FAILED:
        default:
            return EXCH_ACT_FINISHED;
        }
    }
}

void exch_started(struct exch *x, uint32_t now_ms)
{
    x->state = EXCH_SENDING;
    x->attempts++;
    if (x->attempts == 1u) {
        x->counters->sent_first++;
        x->first_send_ms = now_ms;
    } else {
        x->counters->retries++;
    }
    x->last_send_ms = now_ms;
}

void exch_sent(struct exch *x, uint32_t now_ms, uint32_t n_resp)
{
    if (x->state != EXCH_SENDING) {
        return; /* already answered, or aborted by an EDGE_BUSY reply */
    }
    x->timeout_ms = exch_response_timeout_ms(&x->cfg, n_resp);
    x->deadline_ms = now_ms + x->timeout_ms;
    x->state = EXCH_WAITING;
}

void exch_send_aborted(struct exch *x, uint32_t now_ms, bool stall)
{
    if (x->state != EXCH_SENDING) {
        return;
    }
    if (stall) {
        x->counters->tx_stall++;
    } else {
        x->counters->disconnect_abort++;
    }
    attempt_failed(x, now_ms);
}

void exch_disconnected(struct exch *x, uint32_t now_ms)
{
    /* While SENDING the binding reports the abort itself (exch_send_aborted). */
    if (x->state == EXCH_WAITING) {
        x->counters->disconnect_abort++;
        attempt_failed(x, now_ms);
    }
}

/* A request is waiting for its answer once it has been transmitted at least once. */
static bool awaiting(const struct exch *x)
{
    return x->attempts > 0u && !exch_finished(x);
}

enum exch_rx_kind exch_on_frame(struct exch *x, bool echo_mode, uint8_t stream,
                                const uint8_t *frame, size_t length, const uint8_t *sent,
                                size_t sent_length, uint32_t now_ms)
{
    struct exch_counters *c = x->counters;

    if (stream != (echo_mode ? FRAG_STREAM_ECHO : FRAG_STREAM_I1)) {
        c->wrong_stream++; /* binding §9: never read an echo as a response, or vice versa */
        return EXCH_RX_DROPPED;
    }
    if (length < FRAG_MIN_FRAME || memcmp(frame, "I1PK", 4) != 0 || get32(frame + 12) != length) {
        c->invalid_response++;
        return EXCH_RX_DROPPED;
    }
    if (get32(frame + length - 4u) != i1v2_crc32(frame, length - 4u)) {
        c->crc_fail++;
        return EXCH_RX_DROPPED;
    }
    const uint32_t request_id = get32(frame + 16);
    if (!awaiting(x) || request_id != x->request_id) {
        if (request_id != 0u &&
            (request_id == x->request_id || request_id == x->last_finished_id)) {
            c->duplicate_response++;
        } else {
            c->stale_response++;
        }
        return EXCH_RX_DROPPED;
    }
    if (echo_mode) {
        if (length != sent_length || memcmp(frame, sent, length) != 0) {
            c->byte_mismatch++;
            return EXCH_RX_DROPPED;
        }
        c->completed++;
        finish(x, EXCH_DONE, now_ms);
        return EXCH_RX_MATCH;
    }
    struct i1v2_response response;
    if (i1v2_parse_response(frame, length, x->request_id, FRAG_MAX_FRAME, &response) != 0) {
        c->invalid_response++;
        return EXCH_RX_DROPPED;
    }
    x->final_status = response.status;
    if (response.status == I1_OK) {
        memcpy(x->logits, response.logits, sizeof(x->logits));
        c->completed++;
        finish(x, EXCH_DONE, now_ms);
        return EXCH_RX_MATCH;
    }
    if (response.status == I1_EDGE_BUSY) {
        /* Binding §6: a failed attempt, retried after backoff. */
        c->edge_busy++;
        if (x->state == EXCH_SENDING || x->state == EXCH_WAITING) {
            attempt_failed(x, now_ms);
        }
        return EXCH_RX_EDGE_BUSY;
    }
    c->error_final++;
    finish(x, EXCH_ERROR, now_ms);
    return EXCH_RX_ERROR_FINAL;
}
