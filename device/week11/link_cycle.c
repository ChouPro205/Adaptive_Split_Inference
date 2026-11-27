/* See link_cycle.h. The ECHO body is week10/ble_cycle.c exchange() (D2/D3 order, sender-thread D2, no
 * retry) with the echo frame and its answer in place of the I1 request and response. */
#include "link_cycle.h"

#include <errno.h>
#include <string.h>

#include <cmsis_core.h>
#include <zephyr/kernel.h>
#include <zephyr/random/random.h>

#include "ble_link.h"
#include "echo_frames.h"
#include "frag.h"
#include "marker_ctrl.h"
#include "markers.h"
#include "s0c.h"
/* The only translation unit that includes the generated set (100 x 360 FP32) and the plan. */
#include "week8_inputs.h"
#include "week11_link_plan.h"
#include "link_plan_bytes.h"

#define CPU_HZ 64000000u
#define REFUSED_PULSES 5u
#define MARKER_LINK MARKER_PROTECTION   /* D1 = link procedure in week 11 */

BUILD_ASSERT(WEEK8_SAMPLE_COUNT == 100U, "W8-D3: 100 samples");
BUILD_ASSERT(WEEK11_LINK_STATES >= 1U, "the plan needs the base state");

/* Kept in every image (check_week11_build.py), also without a console. */
static const char set_tag[] = "WEEK11_SET_SHA256=" WEEK8_SET_SHA256;
static const char plan_tag[] = "WEEK11_LINK_PLAN_SHA256=" WEEK11_LINK_PLAN_SHA256;
static const char s0c_tag[] = "WEEK11_S0C_VERSION=" S0C_VERSION;

const char *const link_error_names[LINK_E_COUNT] = {
	"OK", "ARGUMENT", "NOT_READY", "TX", "TIMEOUT", "DISCONNECT", "MISMATCH", "REFUSED", "S0C", "HCI",
};
const char *const link_op_names[LINK_OP_COUNT] = {"STATE", "IDLE", "ECHO", "S0C", "RECONNECT"};

static uint8_t tx_frame[ECHO_FRAME_MAX];
static uint8_t expected_ack[ECHO_ACK_LENGTH];
static uint32_t last_request_id;
static struct s0c_beat s0c_out;

unsigned link_plan_entries(void)
{
	return WEEK11_LINK_PLAN_ENTRIES;
}

const char *link_plan_sha256(void)
{
	return WEEK11_LINK_PLAN_SHA256;
}

void link_plan_digest(char out[65])
{
	link_plan_digest_hex(out);
}

unsigned link_states(void)
{
	return WEEK11_LINK_STATES;
}

const char *link_set_sha256(void)
{
	return WEEK8_SET_SHA256;
}

unsigned link_sample_count(void)
{
	return WEEK8_SAMPLE_COUNT;
}

uint32_t link_cycle_now(void)
{
	__asm__ volatile("" ::: "memory");
	const uint32_t cycles = DWT->CYCCNT;
	__asm__ volatile("" ::: "memory");
	return cycles;
}

void link_cycle_init(void)
{
	(void)week8_sample_ids;
	(void)week8_reference_labels;
	__asm__ volatile("" : : "r"(set_tag), "r"(plan_tag), "r"(s0c_tag) : "memory");
	do {
		(void)sys_csrand_get(&last_request_id, sizeof(last_request_id));
	} while (last_request_id == 0u || last_request_id == UINT32_MAX);
	link_rx_configure(1U << FRAG_STREAM_ECHO);
}

static uint32_t next_request_id(void)
{
	++last_request_id;
	if (last_request_id == 0u || last_request_id == UINT32_MAX) {
		last_request_id = 1u;
	}
	return last_request_id;
}

/* D4: one pulse of at least CONFIG_WEEK11_CTRL_MIN_US, rising edge at t0 (taken by the caller). */
static void ctrl_end(uint32_t t0, struct link_result *r)
{
	while (link_cycle_now() - t0 < (uint32_t)CONFIG_WEEK11_CTRL_MIN_US * (CPU_HZ / 1000000u)) {
	}
	const uint32_t t1 = link_cycle_now();
	marker_ctrl_off();
	r->ctrl_cycles = t1 - t0;
}

static void begin(struct link_result *r, unsigned index, uint8_t op, uint8_t state, uint16_t a, uint16_t b)
{
	memset(r, 0, sizeof(*r));
	r->index = index;
	r->op = op;
	r->state = state;
	r->a = a;
	r->b = b;
}

static void drop_stale_frames(void)
{
	const uint8_t *frame;
	uint16_t length;
	uint8_t stream;
	while (link_rx_take(&frame, &length, &stream)) {
		link_rx_release();
	}
}

/* ------------------------------------------------------------------ STATE */

struct target {
	uint8_t phy;
	uint16_t interval_1250us;
	uint16_t latency;
	uint16_t timeout_10ms;
	uint8_t tx_octets;
	int8_t tx_power_dbm;
};

static bool params_equal(const struct link_info *li, const struct target *t)
{
	return li->interval_1250us == t->interval_1250us && li->latency == t->latency &&
	       li->timeout_10ms == t->timeout_10ms;
}

static bool phy_equal(const struct link_info *li, const struct target *t)
{
	const uint8_t phy = link_gap_phy(t->phy);
	return li->tx_phy == phy && li->rx_phy == phy;
}

static bool len_equal(const struct link_info *li, const struct target *t)
{
	return li->tx_data_len == t->tx_octets;
}

/* Waits until done(info) or the deadline; false on timeout or disconnection. */
static bool wait_for(bool (*done)(const struct link_info *, const struct target *), const struct target *t,
		     uint32_t deadline, uint32_t disconnections)
{
	for (;;) {
		struct link_info li;
		link_get_info(&li);
		if (done(&li, t)) {
			return true;
		}
		if (link_disconnections() != disconnections || (int32_t)(k_uptime_get_32() - deadline) >= 0) {
			return false;
		}
		(void)k_sem_take(&link_wake, K_MSEC(50));
	}
}

/* Connection parameters, PHY, data length, TX power, latency mode back to enabled; inside D1. */
static enum link_error apply(const struct target *t, struct link_result *r)
{
	const uint32_t disconnections = link_disconnections();
	const uint32_t deadline = k_uptime_get_32() + CONFIG_WEEK11_STATE_TIMEOUT_MS;
	struct link_info li;
	bool granted = true;
	int err;

	link_get_info(&li);
	if (!li.connected) {
		return LINK_E_NOT_READY;
	}
	if (!params_equal(&li, t)) {
		err = link_request_conn_params(t->interval_1250us, t->interval_1250us, t->latency,
					       t->timeout_10ms);
		r->hci_err = r->hci_err != 0 ? r->hci_err : err;
		granted &= err == 0 && wait_for(params_equal, t, deadline, disconnections);
	}
	link_get_info(&li);
	if (!phy_equal(&li, t)) {
		err = link_request_phy(t->phy);
		r->hci_err = r->hci_err != 0 ? r->hci_err : err;
		granted &= err == 0 && wait_for(phy_equal, t, deadline, disconnections);
	}
	link_get_info(&li);
	if (!len_equal(&li, t)) {
		err = link_request_data_len(t->tx_octets);
		r->hci_err = r->hci_err != 0 ? r->hci_err : err;
		granted &= err == 0 && wait_for(len_equal, t, deadline, disconnections);
	}
	int8_t selected = 0;
	err = link_set_tx_power(t->tx_power_dbm, &selected);
	r->hci_err = r->hci_err != 0 ? r->hci_err : err;
	granted &= err == 0 && selected == t->tx_power_dbm;
	err = link_set_latency_mode(LINK_LATENCY_ENABLE);
	r->hci_err = r->hci_err != 0 ? r->hci_err : err;
	granted &= err == 0;

	link_get_info(&li);
	r->interval_1250us = li.interval_1250us;
	r->latency = li.latency;
	r->timeout_10ms = li.timeout_10ms;
	r->tx_phy = li.tx_phy;
	r->rx_phy = li.rx_phy;
	r->tx_data_len = li.tx_data_len;
	r->tx_power_dbm = li.tx_power_dbm;
	granted &= params_equal(&li, t) && phy_equal(&li, t) && len_equal(&li, t);
	if (link_disconnections() != disconnections) {
		return LINK_E_DISCONNECT;
	}
	return granted ? LINK_OK : (r->hci_err != 0 ? LINK_E_HCI : LINK_E_REFUSED);
}

static void refused_signature(void)
{
	for (unsigned i = 0; i < REFUSED_PULSES; ++i) {
		k_busy_wait(1000);
		marker_ctrl_on();
		k_busy_wait(1000);
		marker_ctrl_off();
	}
}

static void run_state(const struct target *t, struct link_result *r)
{
	marker_ctrl_on();
	const uint32_t t0 = link_cycle_now();
	ctrl_end(t0, r);
	marker_on(MARKER_LINK);
	const uint32_t m0 = k_uptime_get_32();
	r->error = apply(t, r);
	r->link_ms = k_uptime_get_32() - m0;
	marker_off(MARKER_LINK);
	if (r->error != LINK_OK) {
		refused_signature();
	}
	k_msleep(CONFIG_WEEK11_STATE_SETTLE_MS);
}

static struct target target_of(unsigned state)
{
	const struct week11_link_state *s = &week11_link_states[state];
	return (struct target){s->phy, s->interval_1250us, s->latency, s->timeout_10ms, s->tx_octets,
			       s->tx_power_dbm};
}

/* ------------------------------------------------------------------ IDLE, S0C */

static void run_idle(uint16_t ms, struct link_result *r)
{
	marker_ctrl_on();
	const uint32_t t0 = link_cycle_now();
	ctrl_end(t0, r);
	k_msleep(ms);
	r->error = LINK_OK;
}

int link_s0c_of(unsigned n, uint8_t *body, uint16_t *body_len, uint8_t scale_le[2], uint8_t *k)
{
	if (n >= WEEK8_SAMPLE_COUNT) {
		return -EINVAL;
	}
	struct s0c_beat beat;
	if (s0c_encode(week8_inputs[n], &beat) != S0C_OK) {
		return -EIO;
	}
	memcpy(body, beat.body, beat.body_len);
	*body_len = beat.body_len;
	memcpy(scale_le, beat.scale_le, 2);
	*k = beat.k;
	return 0;
}

static void run_s0c(uint16_t sample, uint16_t repeat, struct link_result *r)
{
	marker_ctrl_on();
	const uint32_t t0 = link_cycle_now();
	const bool valid = sample < WEEK8_SAMPLE_COUNT && repeat >= 1u;
	ctrl_end(t0, r);
	if (!valid) {
		r->error = LINK_E_ARGUMENT;
		return;
	}
	int status = S0C_OK;
	marker_on(MARKER_HEAD);
	const uint32_t h0 = link_cycle_now();
	for (unsigned i = 0; i < repeat && status == S0C_OK; ++i) {
		status = s0c_encode(week8_inputs[sample], &s0c_out);
	}
	const uint32_t h1 = link_cycle_now();
	marker_off(MARKER_HEAD);
	r->head_cycles = h1 - h0;
	r->body_len = s0c_out.body_len;
	r->rice_k = s0c_out.k;
	r->error = status == S0C_OK ? LINK_OK : LINK_E_S0C;
}

/* ------------------------------------------------------------------ ECHO */

static bool answer_ok(const uint8_t *frame, uint16_t length, bool ack, uint16_t sent_length)
{
	if (ack) {
		return length == ECHO_ACK_LENGTH && memcmp(frame, expected_ack, ECHO_ACK_LENGTH) == 0;
	}
	return length == sent_length && memcmp(frame, tx_frame, sent_length) == 0;
}

static void run_echo(uint16_t length, uint16_t flags, struct link_result *r)
{
	const bool ack = (flags & LINK_ECHO_ACK) != 0u;
	const bool latency_off = (flags & LINK_ECHO_LATENCY_OFF) != 0u;

	/* D4: frame and expected ack built here, outside TX/WAIT. */
	marker_ctrl_on();
	const uint32_t t0 = link_cycle_now();
	r->request_id = next_request_id();
	r->frame_length = (uint16_t)echo_frame_build(tx_frame, sizeof(tx_frame), length, r->request_id, ack);
	if (r->frame_length != 0u && ack) {
		echo_ack_build(tx_frame, r->frame_length, expected_ack);
	}
	drop_stale_frames();
	ctrl_end(t0, r);
	if (r->frame_length == 0u || (flags & ~(LINK_ECHO_ACK | LINK_ECHO_LATENCY_OFF)) != 0u) {
		r->error = LINK_E_ARGUMENT;
		return;
	}
	if (!link_ready()) {
		r->error = LINK_E_NOT_READY;
		return;
	}

	/* D2 TX: the sender thread clears D2 after the last completion. */
	marker_on(MARKER_TX);
	const uint32_t t4 = link_cycle_now();
	const uint32_t disconnections = link_disconnections();
	if (link_send(tx_frame, r->frame_length, FRAG_STREAM_ECHO) != 0) {
		marker_off(MARKER_TX);
		r->error = LINK_E_TX;
		return;
	}
	struct link_tx_result tx;
	while (!link_tx_take_result(&tx)) {
		(void)k_sem_take(&link_wake, K_MSEC(50));
	}
	marker_off(MARKER_TX);

	/* D3 WAIT */
	marker_on(MARKER_WAIT);
	const uint32_t t5 = link_cycle_now();
	r->tx_cycles = t5 - t4;
	r->att_mtu = tx.att_mtu;
	r->fragments = tx.fragments;
	r->enomem_retries = tx.enomem_retries;
	enum link_error error = LINK_OK;
	if (latency_off && link_set_latency_mode(LINK_LATENCY_DISABLE) != 0) {
		error = LINK_E_HCI;
	}
	if (tx.status != LINK_TX_DONE) {
		error = tx.status == LINK_TX_NOTCONN ? LINK_E_DISCONNECT : LINK_E_TX;
	} else if (error == LINK_OK) {
		const uint32_t deadline = k_uptime_get_32() + CONFIG_WEEK11_ECHO_TIMEOUT_MS;
		for (;;) {
			const uint8_t *frame;
			uint16_t got;
			uint8_t stream;
			if (link_rx_take(&frame, &got, &stream)) {
				const bool ok = stream == FRAG_STREAM_ECHO &&
						answer_ok(frame, got, ack, r->frame_length);
				link_rx_release();
				if (ok) {
					break;
				}
				r->invalid_answers++;
				continue;
			}
			if (link_disconnections() != disconnections) {
				error = LINK_E_DISCONNECT;
				break;
			}
			const uint32_t now = k_uptime_get_32();
			if ((int32_t)(now - deadline) >= 0) {
				error = r->invalid_answers != 0u ? LINK_E_MISMATCH : LINK_E_TIMEOUT;
				break;
			}
			link_rx_tick(now);
			(void)k_sem_take(&link_wake, K_MSEC(MIN(deadline - now, 50u)));
		}
	}
	if (latency_off && link_disconnections() == disconnections &&
	    link_set_latency_mode(LINK_LATENCY_ENABLE) != 0 && error == LINK_OK) {
		error = LINK_E_HCI;
	}
	const uint32_t t6 = link_cycle_now();
	marker_off(MARKER_WAIT);
	r->wait_cycles = t6 - t5;
	r->error = error;
}

/* ------------------------------------------------------------------ RECONNECT */

static void run_reconnect(struct link_result *r)
{
	marker_ctrl_on();
	const uint32_t t0 = link_cycle_now();
	ctrl_end(t0, r);
	if (!link_ready()) {
		r->error = LINK_E_NOT_READY;
		return;
	}
	marker_on(MARKER_LINK);
	const uint32_t m0 = k_uptime_get_32();
	const uint32_t deadline = m0 + CONFIG_WEEK11_RECONNECT_TIMEOUT_MS;
	const uint32_t disconnections = link_disconnections();
	enum link_error error = link_drop() == 0 ? LINK_OK : LINK_E_HCI;
	while (error == LINK_OK && link_disconnections() == disconnections) {
		if ((int32_t)(k_uptime_get_32() - deadline) >= 0) {
			error = LINK_E_TIMEOUT;
			break;
		}
		(void)k_sem_take(&link_wake, K_MSEC(50));
	}
	/* Ready = connected + subscribed + ATT MTU of the build (BlueZ exchanges it on connect). */
	while (error == LINK_OK && !(link_ready() && link_mtu() >= CONFIG_BT_L2CAP_TX_MTU)) {
		if ((int32_t)(k_uptime_get_32() - deadline) >= 0) {
			error = LINK_E_TIMEOUT;
			break;
		}
		(void)k_sem_take(&link_wake, K_MSEC(50));
	}
	if (error == LINK_OK) {
		/* The base state again, inside D1: part of the cost of a reconnect. The peripheral parameter
		 * update timer of the new connection (5 s) bounds how fast the interval returns. */
		const struct target t = target_of(LINK_BASE_STATE);
		error = apply(&t, r);
	}
	r->link_ms = k_uptime_get_32() - m0;
	marker_off(MARKER_LINK);
	r->error = error;
}

/* ------------------------------------------------------------------ dispatch */

void link_run_op(uint8_t op, uint8_t state, uint16_t a, uint16_t b, struct link_result *r)
{
	begin(r, 0u, op, state, a, b);
	if (state >= WEEK11_LINK_STATES) {
		marker_ctrl_on();
		ctrl_end(link_cycle_now(), r);
		r->error = LINK_E_ARGUMENT;
		return;
	}
	switch (op) {
	case LINK_OP_STATE: {
		const struct target t = target_of(state);
		run_state(&t, r);
		break;
	}
	case LINK_OP_IDLE:
		run_idle(a, r);
		break;
	case LINK_OP_ECHO:
		run_echo(a, b, r);
		break;
	case LINK_OP_S0C:
		run_s0c(a, b, r);
		break;
	case LINK_OP_RECONNECT:
		run_reconnect(r);
		break;
	default:
		marker_ctrl_on();
		ctrl_end(link_cycle_now(), r);
		r->error = LINK_E_ARGUMENT;
		break;
	}
}

void link_run_state_values(uint8_t phy, uint16_t interval_1250us, uint16_t latency, uint8_t tx_octets,
			   int8_t tx_power_dbm, struct link_result *r)
{
	begin(r, 0u, LINK_OP_STATE, 255u, interval_1250us, latency);
	const struct target t = {phy, interval_1250us, latency, 400u, tx_octets, tx_power_dbm};
	run_state(&t, r);
}

void link_run_entry(unsigned index, struct link_result *r)
{
	if (index >= WEEK11_LINK_PLAN_ENTRIES) {
		begin(r, index, LINK_OP_COUNT, 0u, 0u, 0u);
		r->error = LINK_E_ARGUMENT;
		return;
	}
	const struct week11_link_entry *e = &week11_link_plan[index];
	link_run_op(e->op, e->state, e->a, e->b, r);
	r->index = index;
}
