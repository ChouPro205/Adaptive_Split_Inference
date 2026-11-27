/*
 * Week 11 link ops (W11-D2, W11-D3): one entry of the link plan (week11_link_plan.h) over the connected link.
 * Markers (W7-D2 pins; D1 is a link procedure in week 11, never protection):
 *   D4 CTRL   every op starts with one pulse (padded to CONFIG_WEEK11_CTRL_MIN_US); ECHO builds its frame and
 *             expected ack inside it. A STATE the central did not grant ends with 5 extra 1 ms CTRL pulses.
 *   D1 LINK   STATE: from the first request until every parameter equals the plan or the timeout;
 *             RECONNECT: from the device's disconnect until the link is ready again in the base state
 *   D2 TX     ECHO: link_send() until the last notify completes (the sender thread clears it)
 *   D3 WAIT   ECHO: until the answer (ECHO-ACK v1 or the whole frame) has been verified, or the timeout;
 *             with ECHO_LATENCY_OFF the latency mode is disabled at its start and enabled at its end
 *   D0 HEAD   S0C: b x s0c_encode() of W8-D3 input a
 *   IDLE      only the CTRL pulse, then a ms of connected idle
 * No retry. The op gap (CONFIG_WEEK11_OP_GAP_MS) follows every op except STATE (own settle) and IDLE.
 */
#ifndef WEEK11_LINK_CYCLE_H
#define WEEK11_LINK_CYCLE_H

#include <stdbool.h>
#include <stdint.h>

#define LINK_OP_STATE 0u
#define LINK_OP_IDLE 1u
#define LINK_OP_ECHO 2u
#define LINK_OP_S0C 3u
#define LINK_OP_RECONNECT 4u
#define LINK_OP_COUNT 5u
#define LINK_ECHO_ACK 0x01u
#define LINK_ECHO_LATENCY_OFF 0x02u
#define LINK_BASE_STATE 0u

enum link_error {
	LINK_OK,
	LINK_E_ARGUMENT,
	LINK_E_NOT_READY,
	LINK_E_TX,
	LINK_E_TIMEOUT,
	LINK_E_DISCONNECT,
	LINK_E_MISMATCH,      /* answer received but not the expected ack/frame (counted, WAIT goes on) */
	LINK_E_REFUSED,       /* STATE: not every parameter granted before the timeout */
	LINK_E_S0C,
	LINK_E_HCI,           /* a VS/HCI command failed */
	LINK_E_COUNT
};

extern const char *const link_error_names[LINK_E_COUNT];
extern const char *const link_op_names[LINK_OP_COUNT];

struct link_result {
	enum link_error error;
	unsigned index;
	uint8_t op;
	uint8_t state;
	uint16_t a;
	uint16_t b;
	uint32_t ctrl_cycles;
	/* STATE / RECONNECT: what the link has at the end of D1 */
	uint16_t interval_1250us;
	uint16_t latency;
	uint16_t timeout_10ms;
	uint8_t tx_phy;
	uint8_t rx_phy;
	uint16_t tx_data_len;
	int8_t tx_power_dbm;
	int hci_err;          /* first failing request (0 when none) */
	uint32_t link_ms;     /* D1 duration */
	/* ECHO */
	uint32_t request_id;
	uint16_t frame_length;
	uint16_t att_mtu;
	uint16_t fragments;
	uint32_t enomem_retries;
	uint32_t tx_cycles;
	uint32_t wait_cycles;
	uint32_t invalid_answers;
	/* S0C */
	uint16_t body_len;
	uint8_t rice_k;
	uint32_t head_cycles;
};

/* Plan (week11_link_plan.h) and the W8-D3 set. */
unsigned link_plan_entries(void);
const char *link_plan_sha256(void);
void link_plan_digest(char out[65]);   /* computed on the device: equal to link_plan_sha256() when intact */
unsigned link_states(void);
const char *link_set_sha256(void);
unsigned link_sample_count(void);      /* W8-D3 samples available to S0C (100) */

uint32_t link_cycle_now(void);
/* Random non-zero request_id start, reassembler restricted to stream 0x02. Call after link_init(). */
void link_cycle_init(void);
/* Entry i of the plan. */
void link_run_entry(unsigned index, struct link_result *r);
/* One op outside the plan (console), the same bodies. */
void link_run_op(uint8_t op, uint8_t state, uint16_t a, uint16_t b, struct link_result *r);
/* STATE with explicit parameters (console STATEX); state index 255. */
void link_run_state_values(uint8_t phy, uint16_t interval_1250us, uint16_t latency, uint8_t tx_octets,
			   int8_t tx_power_dbm, struct link_result *r);
/* S0c of W8-D3 sample n (console VERIFY): 0 on success. */
int link_s0c_of(unsigned n, uint8_t *body, uint16_t *body_len, uint8_t scale_le[2], uint8_t *k);

#endif
