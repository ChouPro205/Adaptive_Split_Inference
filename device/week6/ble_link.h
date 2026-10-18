/*
 * Zephyr side of I1 BLE binding v1: GATT service (§2), notify sender thread with TX credits
 * (§4.3) and the RX write callback feeding the reassembler (§5). Callbacks only update state
 * and give link_wake; the application thread polls the state, so no event can be lost.
 */
#ifndef WEEK6_BLE_LINK_H
#define WEEK6_BLE_LINK_H

#include <stdbool.h>
#include <stdint.h>
#include <zephyr/kernel.h>

#include "frag.h"

#define LINK_TX_CREDITS 4
#define LINK_TX_CREDIT_TIMEOUT_MS 2000

enum link_tx_status { LINK_TX_DONE, LINK_TX_STALL, LINK_TX_NOTCONN };

struct link_tx_result {
    enum link_tx_status status;
    uint16_t transfer_id;
    uint16_t att_mtu;
    uint16_t fragments;
    uint32_t start_ms;       /* first notify call */
    uint32_t done_ms;        /* completion callback of the last fragment: timeout start (§6) */
    uint32_t cycles;         /* DWT cycles from first notify call to last completion */
    uint32_t enomem_retries; /* -ENOMEM/-ENOBUFS back-offs of 2 ms */
};

struct link_info {
    bool connected;
    bool subscribed;
    uint16_t att_mtu;
    uint16_t interval_1250us;
    uint16_t latency;
    uint16_t timeout_10ms;
    uint8_t tx_phy;
    uint8_t rx_phy;
    uint16_t tx_data_len;
    uint16_t rx_data_len;
    uint32_t connections;
    uint32_t disconnections;
    uint8_t last_disconnect_reason;
    uint32_t rx_writes;
    uint32_t rx_bytes;
    uint32_t notifications;
};

/* Given by every callback that changes link, TX or RX state. */
extern struct k_sem link_wake;

int link_init(void);
bool link_ready(void);
uint16_t link_mtu(void);
void link_get_info(struct link_info *info);
/* Increments on every disconnection (compare against a remembered value). */
uint32_t link_disconnections(void);
int link_disconnect(void);
/* Asks the central for new connection parameters (units 1.25 ms / 10 ms); the central decides. */
int link_request_conn_params(uint16_t min_1250us, uint16_t max_1250us, uint16_t latency,
                             uint16_t timeout_10ms);

/* Queues one frame for the sender thread; -EBUSY if a transfer is still running. */
int link_send(const uint8_t *frame, uint16_t length, uint8_t stream);
bool link_tx_busy(void);
/* true once per finished transfer, with its result. */
bool link_tx_take_result(struct link_tx_result *result);

/* Streams accepted by the reassembler (bit 1 << stream). */
void link_rx_configure(uint8_t stream_mask);
/* A complete frame stays valid until link_rx_release(). */
bool link_rx_take(const uint8_t **frame, uint16_t *length, uint8_t *stream);
void link_rx_release(void);
void link_rx_tick(uint32_t now_ms);
void link_rx_counters(uint32_t out[REASM_COUNTER_COUNT]);
void link_rx_reset_counters(void);

/* DWT cycle counter (enabled by link_init). */
uint32_t link_cycles(void);

#endif
