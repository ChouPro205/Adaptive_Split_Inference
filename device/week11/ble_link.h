/*
 * Week 11 link layer: the week 6 API (../week6/ble_link.h, I1 BLE binding v1 §2-§5) plus the link-state
 * controls of W11-D3 (PHY, data length, TX power, peripheral latency mode, RSSI) and a disconnect that keeps
 * advertising (reconnect cycles). Callbacks only update state and give link_wake; the application thread
 * polls, so no event can be lost. Implementation: ble_link.c (fork of week8/ble_link.c, hash-locked).
 */
#ifndef WEEK11_BLE_LINK_H
#define WEEK11_BLE_LINK_H

#include <stdbool.h>
#include <stdint.h>
#include <zephyr/kernel.h>

#include "frag.h"

#define LINK_TX_CREDITS 4
#define LINK_TX_CREDIT_TIMEOUT_MS 2000

/* Plan PHY codes (week11_common.py). */
#define LINK_PHY_1M 1u
#define LINK_PHY_2M 2u
#define LINK_PHY_CODED_S8 3u

/* sdc_hci_vs_peripheral_latency_mode. */
#define LINK_LATENCY_ENABLE 0u
#define LINK_LATENCY_DISABLE 1u

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
    uint8_t tx_phy;          /* BT_GAP_LE_PHY_* (1 = 1M, 2 = 2M, 4 = Coded) */
    uint8_t rx_phy;
    uint16_t tx_data_len;
    uint16_t rx_data_len;
    int8_t tx_power_dbm;     /* last selected_tx_power of the VS command (0 = build default) */
    uint8_t latency_mode;    /* last mode set (LINK_LATENCY_*) */
    uint32_t connections;
    uint32_t disconnections;
    uint8_t last_disconnect_reason;
    uint32_t param_updates;  /* le_param_updated callbacks */
    uint32_t phy_updates;
    uint32_t data_len_updates;
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
/* The device ends its session: advertising closed until the next reboot (W8-D2). */
int link_disconnect(void);
/* Reconnect cycle: disconnect, advertising restarts once the connection object is released. */
int link_drop(void);
/* Asks the central for new connection parameters (units 1.25 ms / 10 ms); the central decides. */
int link_request_conn_params(uint16_t min_1250us, uint16_t max_1250us, uint16_t latency,
                             uint16_t timeout_10ms);
/* LL PHY update to a plan PHY code (Coded: S8 preferred for TX). */
int link_request_phy(uint8_t plan_phy);
/* LL data length update: 27 or 251 octets (TX time = the Coded maximum for that length). */
int link_request_data_len(uint16_t tx_octets);
/* Zephyr VS Write TX Power Level of the connection; *selected = the controller's choice. */
int link_set_tx_power(int8_t dbm, int8_t *selected);
/* SDC VS peripheral latency mode (LINK_LATENCY_*); about one HCI round trip. */
int link_set_latency_mode(uint8_t mode);
/* HCI Read RSSI of the connection (dBm). */
int link_read_rssi(int8_t *rssi);
/* BT_GAP_LE_PHY_* of a plan PHY code. */
uint8_t link_gap_phy(uint8_t plan_phy);

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
