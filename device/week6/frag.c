/* See frag.h. Mirrors Reassembler.feed() of contracts/i1v2_ref/i1_ble_binding.py step by step. */
#include "frag.h"

#include <string.h>

const char *const reasm_counter_names[REASM_COUNTER_COUNT] = {
    "malformed_fragment", "inconsistent_fragment", "orphan_fragment", "duplicate_fragment",
    "superseded_transfer", "overlap_conflict", "gap", "frame_header_mismatch",
    "reassembly_timeout", "disconnect", "rx_busy", "aborted_transfers", "frames_delivered",
};

static uint16_t get16(const uint8_t *p)
{
    return (uint16_t)(p[0] | ((uint16_t)p[1] << 8));
}

static uint32_t get32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

uint16_t frag_data_bytes(uint16_t att_mtu)
{
    if (att_mtu < FRAG_MIN_ATT_MTU) {
        return 0;
    }
    return (uint16_t)(att_mtu - FRAG_ATT_OVERHEAD - FRAG_HEADER);
}

uint32_t frag_count(uint32_t frame_length, uint16_t att_mtu)
{
    const uint32_t chunk = frag_data_bytes(att_mtu);
    return chunk == 0u ? 0u : (frame_length + chunk - 1u) / chunk;
}

void frag_write_header(uint8_t out[FRAG_HEADER], uint8_t stream, uint16_t transfer_id,
                       uint16_t offset, uint16_t total_length)
{
    out[0] = FRAG_VERSION;
    out[1] = stream;
    out[2] = (uint8_t)transfer_id;
    out[3] = (uint8_t)(transfer_id >> 8);
    out[4] = (uint8_t)offset;
    out[5] = (uint8_t)(offset >> 8);
    out[6] = (uint8_t)total_length;
    out[7] = (uint8_t)(total_length >> 8);
}

uint16_t frag_next_transfer_id(uint16_t *last)
{
    *last = (uint16_t)(*last % 0xffffu + 1u);
    return *last;
}

static void count(struct reasm *r, enum reasm_counter c)
{
    r->counters[c]++;
}

static void reset_transfer(struct reasm *r)
{
    r->active = false;
    r->stream = 0;
    r->transfer_id = 0;
    r->total = 0;
    r->received = 0;
    r->header_checked = false;
    r->last_ms = 0;
}

static void abort_transfer(struct reasm *r, enum reasm_counter reason)
{
    count(r, reason);
    count(r, REASM_ABORTED_TRANSFERS);
    reset_transfer(r);
}

static void start(struct reasm *r, uint8_t stream, uint16_t transfer_id, uint16_t total,
                  uint32_t now_ms)
{
    r->active = true;
    r->stream = stream;
    r->transfer_id = transfer_id;
    r->total = total;
    r->received = 0;
    r->header_checked = false;
    r->last_ms = now_ms;
}

void reasm_init(struct reasm *r, uint8_t *buffer, uint16_t capacity, uint8_t stream_mask,
                uint32_t timeout_ms)
{
    memset(r, 0, sizeof(*r));
    r->buffer = buffer;
    r->capacity = capacity > FRAG_MAX_FRAME ? FRAG_MAX_FRAME : capacity;
    r->stream_mask = stream_mask;
    r->timeout_ms = timeout_ms;
}

void reasm_reset_counters(struct reasm *r)
{
    memset(r->counters, 0, sizeof(r->counters));
}

void reasm_tick(struct reasm *r, uint32_t now_ms)
{
    if (r->active && (uint32_t)(now_ms - r->last_ms) > r->timeout_ms) {
        abort_transfer(r, REASM_REASSEMBLY_TIMEOUT);
    }
}

void reasm_disconnect(struct reasm *r)
{
    if (r->active) {
        abort_transfer(r, REASM_DISCONNECT);
    }
    r->has_last_completed = false;
}

void reasm_release(struct reasm *r)
{
    r->pending = false;
    r->pending_length = 0;
}

static bool stream_accepted(const struct reasm *r, uint8_t stream)
{
    return stream < 8u && (r->stream_mask & (1u << stream)) != 0u;
}

bool reasm_feed(struct reasm *r, const uint8_t *data, uint16_t length, uint32_t now_ms)
{
    reasm_tick(r, now_ms);
    if (length <= FRAG_HEADER) {
        count(r, REASM_MALFORMED_FRAGMENT);
        return false;
    }
    const uint8_t version = data[0];
    const uint8_t stream = data[1];
    const uint16_t transfer_id = get16(data + 2);
    const uint16_t offset = get16(data + 4);
    const uint16_t total = get16(data + 6);
    const uint8_t *chunk = data + FRAG_HEADER;
    const uint32_t chunk_length = (uint32_t)length - FRAG_HEADER;

    if (version != FRAG_VERSION || !stream_accepted(r, stream) || transfer_id == 0u ||
        total < FRAG_MIN_FRAME || total > r->capacity ||
        (uint32_t)offset + chunk_length > total) {
        count(r, REASM_MALFORMED_FRAGMENT);
        if (r->active && r->stream == stream && r->transfer_id == transfer_id) {
            abort_transfer(r, REASM_INCONSISTENT_FRAGMENT);
        }
        return false;
    }
    if (!r->active) {
        if (r->has_last_completed && r->last_stream == stream &&
            r->last_transfer_id == transfer_id) {
            count(r, REASM_DUPLICATE_FRAGMENT);
            return false;
        }
        if (offset != 0u) {
            count(r, REASM_ORPHAN_FRAGMENT);
            return false;
        }
        if (r->pending) {
            /* Rule 8: one request outstanding; the previous frame was not taken yet. */
            count(r, REASM_RX_BUSY);
            return false;
        }
        start(r, stream, transfer_id, total, now_ms);
    } else if (r->stream != stream || r->transfer_id != transfer_id) {
        if (offset != 0u) {
            count(r, REASM_ORPHAN_FRAGMENT);
            return false;
        }
        /* Sender gave up and started a new transfer. */
        abort_transfer(r, REASM_SUPERSEDED_TRANSFER);
        start(r, stream, transfer_id, total, now_ms);
    } else if (total != r->total) {
        abort_transfer(r, REASM_INCONSISTENT_FRAGMENT);
        return false;
    }

    const uint32_t received = r->received;
    if (offset < received) {
        if ((uint32_t)offset + chunk_length <= received &&
            memcmp(r->buffer + offset, chunk, chunk_length) == 0) {
            count(r, REASM_DUPLICATE_FRAGMENT);
            r->last_ms = now_ms;
        } else {
            abort_transfer(r, REASM_OVERLAP_CONFLICT);
        }
        return false;
    }
    if (offset > received) {
        abort_transfer(r, REASM_GAP);
        return false;
    }
    memcpy(r->buffer + received, chunk, chunk_length);
    r->received = (uint16_t)(received + chunk_length);
    r->last_ms = now_ms;
    if (!r->header_checked && r->received >= 16u) {
        if (memcmp(r->buffer, "I1PK", 4) != 0 || get32(r->buffer + 12) != r->total) {
            abort_transfer(r, REASM_FRAME_HEADER_MISMATCH);
            return false;
        }
        r->header_checked = true;
    }
    if (r->received < r->total) {
        return false;
    }
    r->has_last_completed = true;
    r->last_stream = r->stream;
    r->last_transfer_id = r->transfer_id;
    r->pending = true;
    r->pending_stream = r->stream;
    r->pending_length = r->total;
    reset_transfer(r);
    count(r, REASM_FRAMES_DELIVERED);
    return true;
}
