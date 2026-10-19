/*
 * I1 BLE binding v1 fragment header and bounded reassembly (contracts/i1_ble_binding_v1.md
 * §3-§5). Portable C without Zephyr so the host test can run it differentially against
 * contracts/i1v2_ref/i1_ble_binding.py. Not thread-safe: the caller serialises access.
 */
#ifndef WEEK6_FRAG_H
#define WEEK6_FRAG_H

#include <stdbool.h>
#include <stdint.h>

#define FRAG_HEADER 8u
#define FRAG_VERSION 1u
#define FRAG_STREAM_I1 0x01u
#define FRAG_STREAM_ECHO 0x02u
#define FRAG_ATT_OVERHEAD 3u
#define FRAG_MIN_ATT_MTU 23u
#define FRAG_MIN_FRAME 36u
#define FRAG_MAX_FRAME 6380u
#define FRAG_REASSEMBLY_TIMEOUT_MS 2000u

/* Frame bytes per fragment for an ATT MTU (binding §3); 0 below the Bluetooth minimum. */
uint16_t frag_data_bytes(uint16_t att_mtu);
uint32_t frag_count(uint32_t frame_length, uint16_t att_mtu);
void frag_write_header(uint8_t out[FRAG_HEADER], uint8_t stream, uint16_t transfer_id,
                       uint16_t offset, uint16_t total_length);
/* Binding §4.2: 1, 2, ..., 65535, 1, ... (never 0); *last starts at 0 per connection. */
uint16_t frag_next_transfer_id(uint16_t *last);

/* Counter names follow the Python reference Reassembler, plus rx_busy (rule 8). */
enum reasm_counter {
    REASM_MALFORMED_FRAGMENT,
    REASM_INCONSISTENT_FRAGMENT,
    REASM_ORPHAN_FRAGMENT,
    REASM_DUPLICATE_FRAGMENT,
    REASM_SUPERSEDED_TRANSFER,
    REASM_OVERLAP_CONFLICT,
    REASM_GAP,
    REASM_FRAME_HEADER_MISMATCH,
    REASM_REASSEMBLY_TIMEOUT,
    REASM_DISCONNECT,
    REASM_RX_BUSY,
    REASM_ABORTED_TRANSFERS,
    REASM_FRAMES_DELIVERED,
    REASM_COUNTER_COUNT
};

extern const char *const reasm_counter_names[REASM_COUNTER_COUNT];

struct reasm {
    uint8_t *buffer;
    uint16_t capacity;        /* max_frame, <= FRAG_MAX_FRAME */
    uint8_t stream_mask;      /* bit (1 << stream) per accepted stream */
    uint32_t timeout_ms;
    bool active;
    uint8_t stream;
    uint16_t transfer_id;
    uint16_t total;
    uint16_t received;
    bool header_checked;
    uint32_t last_ms;
    bool has_last_completed;
    uint8_t last_stream;
    uint16_t last_transfer_id;
    bool pending;             /* a delivered frame the upper layer has not released yet */
    uint8_t pending_stream;
    uint16_t pending_length;
    uint32_t counters[REASM_COUNTER_COUNT];
};

void reasm_init(struct reasm *r, uint8_t *buffer, uint16_t capacity, uint8_t stream_mask,
                uint32_t timeout_ms);
/* Returns true when a whole frame is ready in r->buffer[0..pending_length). */
bool reasm_feed(struct reasm *r, const uint8_t *data, uint16_t length, uint32_t now_ms);
void reasm_tick(struct reasm *r, uint32_t now_ms);
/* Connection lost: abort the transfer in progress and forget the last completed one. */
void reasm_disconnect(struct reasm *r);
/* Upper layer has consumed the pending frame; the buffer may be reused. */
void reasm_release(struct reasm *r);
void reasm_reset_counters(struct reasm *r);

#endif
