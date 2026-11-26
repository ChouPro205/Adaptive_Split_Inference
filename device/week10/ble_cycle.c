/* See ble_cycle.h. Fork of week8/g2_cycle.c (hash-locked): the CTRL/HEAD/TX/WAIT body is unchanged
 * except that the split comes from the plan entry, rho is always 0 (no PROT phase) and s10 stops after
 * HEAD; the head is week9/dev_cycle.c dev_head() (hash-locked) with the FP32 output kept for s10. */
#include "ble_cycle.h"

#include <string.h>

#include <cmsis_core.h>
#include <zephyr/kernel.h>
#include <zephyr/random/random.h>

#include "ble_link.h"
#include "frag.h"
#include "head_fast.h"
#include "i1v2_codec.h"
#include "marker_ctrl.h"
#include "markers.h"
#include "ble_plan_bytes.h"
#include "packets.h"
#include "quantization.h"
#include "sha256.h"
/* The only translation unit that includes the generated set (100 x 360 FP32 = 144 000 B) and plan. */
#include "week8_inputs.h"
#include "week10_ble_plan.h"

#define CPU_HZ 64000000u
#define WIRE_SPLIT_BASE 256u   /* registry: wire_split_id = 256 + s */

BUILD_ASSERT(WEEK4_SPLIT_COUNT == BLE_SPLITS, "R3 mapping limits differ");
BUILD_ASSERT(WEEK8_SAMPLE_COUNT == 100U, "W8-D3: 100 samples");
BUILD_ASSERT(WEEK10_BLE_PLAN_SPLITS == WEEK4_SPLIT_COUNT, "W10-D4: every round covers every split");
BUILD_ASSERT(WEEK10_BLE_PLAN_ROUNDS <= WEEK8_SAMPLE_COUNT, "round k uses W8-D3 sample k");
BUILD_ASSERT(WEEK10_BLE_PLAN_CYCLES == WEEK10_BLE_PLAN_ROUNDS * WEEK10_BLE_PLAN_SPLITS, "plan size");
BUILD_ASSERT(BLE_MAX_VALUES <= PKT_MAX_PAYLOAD && BLE_MAX_CHANNELS <= PKT_MAX_CHANNELS,
	     "every split must fit one I1 v2 request");

/* Kept in every image (check_week10_build.py), also without a console. */
static const char set_tag[] = "WEEK10_SET_SHA256=" WEEK8_SET_SHA256;
static const char plan_tag[] = "WEEK10_BLE_PLAN_SHA256=" WEEK10_BLE_PLAN_SHA256;

const char *const ble_error_names[BLE_E_COUNT] = {
	"OK", "ARGUMENT", "HEAD", "QUANT", "ENCODE", "NOT_READY", "TX", "TIMEOUT", "DISCONNECT",
	"ERROR_RESPONSE",
};

static int8_t q_buf[BLE_MAX_VALUES];
static uint8_t scale_le_buf[2u * BLE_MAX_CHANNELS];
static uint32_t scale_bits_buf[BLE_MAX_CHANNELS];
static uint8_t tx_frame[FRAG_MAX_FRAME];
static uint32_t last_request_id;
static uint32_t last_quant_cycles;

unsigned ble_sample_count(void)
{
	return WEEK10_BLE_PLAN_ROUNDS;
}

const char *ble_sample_id(unsigned sample)
{
	return sample < WEEK8_SAMPLE_COUNT ? week8_sample_ids[sample] : "?";
}

const char *ble_set_sha256(void)
{
	return WEEK8_SET_SHA256;
}

unsigned ble_plan_cycles(void)
{
	return WEEK10_BLE_PLAN_CYCLES;
}

unsigned ble_plan_split(unsigned cycle)
{
	return cycle < WEEK10_BLE_PLAN_CYCLES ? week10_ble_plan[cycle].split : BLE_SPLITS;
}

unsigned ble_plan_sample(unsigned cycle)
{
	return cycle / WEEK10_BLE_PLAN_SPLITS;
}

const char *ble_plan_sha256(void)
{
	return WEEK10_BLE_PLAN_SHA256;
}

void ble_plan_digest(char out[65])
{
	struct sha256 ctx;
	uint8_t digest[32];
	sha256_init(&ctx);
	for (unsigned i = 0; i < WEEK10_BLE_PLAN_CYCLES; ++i) {
		uint8_t bytes[BLE_PLAN_ENTRY_BYTES];
		ble_plan_entry_bytes(&week10_ble_plan[i], bytes);
		sha256_update(&ctx, bytes, sizeof(bytes));
	}
	sha256_final(&ctx, digest);
	sha256_hex(digest, out);
}

uint32_t ble_cycle_now(void)
{
	__asm__ volatile("" ::: "memory");
	const uint32_t cycles = DWT->CYCCNT;
	__asm__ volatile("" ::: "memory");
	return cycles;
}

uint32_t ble_last_quant_cycles(void)
{
	return last_quant_cycles;
}

uint16_t ble_wire_split_id(unsigned split)
{
	return (uint16_t)(WIRE_SPLIT_BASE + split);
}

int ble_head(unsigned split, unsigned sample, struct ble_tensor *out, uint32_t *head_cycles)
{
	struct week4_result result;
	if (sample >= WEEK8_SAMPLE_COUNT || split >= WEEK4_SPLIT_COUNT) {
		return -3;
	}
	const uint32_t h0 = ble_cycle_now();
	int status = head_fast_run(split, week8_inputs[sample], &result);
	const uint32_t c0 = ble_cycle_now();
	if (head_cycles != NULL) {
		*head_cycles = c0 - h0;
	}
	if (status != 0) {
		return -1;
	}
	const unsigned channels = result.shape.dims[1];
	const unsigned length = result.shape.rank == 3U ? result.shape.dims[2] : 1U;
	if (channels > BLE_MAX_CHANNELS || result.shape.count > BLE_MAX_VALUES ||
	    channels * length != result.shape.count) {
		return -1;
	}
	status = week5_quantize(result.values, result.shape.count, 1, channels, length, q_buf,
				sizeof(q_buf), scale_le_buf, sizeof(scale_le_buf));
	if (status != WEEK5_OK) {
		return -2;
	}
	/* I1 v2 carries each scale as the FP32 value of the FP16 scale (exact widening). */
	for (unsigned c = 0; c < channels; ++c) {
		const uint16_t half = (uint16_t)(scale_le_buf[2u * c] | (scale_le_buf[2u * c + 1u] << 8));
		const float value = week5_f16_to_f32(half);
		memcpy(&scale_bits_buf[c], &value, sizeof(value));
	}
	last_quant_cycles = ble_cycle_now() - c0;
	*out = (struct ble_tensor){split, sample, (uint16_t)channels, length, q_buf, scale_le_buf,
				   scale_bits_buf, result.values};
	return 0;
}

static struct pkt_tensor packet_tensor(const struct ble_tensor *t)
{
	return (struct pkt_tensor){PKT_MODEL_PROFILE_ID, ble_wire_split_id(t->split), t->channels,
				   t->length, t->q, t->scale_bits};
}

size_t ble_request(const struct ble_tensor *t, uint32_t request_id, uint8_t *frame)
{
	const struct pkt_tensor pt = packet_tensor(t);
	return pkt_encode(frame, FRAG_MAX_FRAME, request_id, &pt, (const uint8_t *)t->q, NULL, NULL);
}

void ble_cycle_init(void)
{
	/* W8-D4 labels are for s=2 only and are not used in week 10 (labels: KV260 offline, W8-D8). */
	(void)week8_reference_labels;
	__asm__ volatile("" : : "r"(set_tag), "r"(plan_tag) : "memory");
	/* I1 v2 §11: request_id starts at a random non-zero value after every boot. */
	do {
		(void)sys_csrand_get(&last_request_id, sizeof(last_request_id));
	} while (last_request_id == 0u || last_request_id == UINT32_MAX);
	link_rx_configure(1U << FRAG_STREAM_I1);
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

/* TX + WAIT of one plain request (g2_cycle_run() body from D2 on, rho0). */
static enum ble_error exchange(const struct ble_tensor *tensor, struct ble_result *r)
{
	const struct pkt_tensor pt = packet_tensor(tensor);

	/* D2 TX: encode + CRC + fragments; the sender thread clears D2 after the last completion. */
	marker_on(MARKER_TX);
	const uint32_t t4 = ble_cycle_now();
	r->request_id = pkt_next_request_id(&last_request_id);
	r->frame_length = pkt_encode(tx_frame, sizeof(tx_frame), r->request_id, &pt,
				     (const uint8_t *)tensor->q, NULL, NULL);
	r->encode_cycles = ble_cycle_now() - t4;
	if (r->frame_length == 0u) {
		marker_off(MARKER_TX);
		return BLE_E_ENCODE;
	}
	if (!link_ready()) {
		marker_off(MARKER_TX);
		return BLE_E_NOT_READY;
	}
	drop_stale_frames();
	const uint32_t disconnections = link_disconnections();
	if (link_send(tx_frame, (uint16_t)r->frame_length, FRAG_STREAM_I1) != 0) {
		marker_off(MARKER_TX);
		return BLE_E_TX;
	}
	struct link_tx_result tx;
	while (!link_tx_take_result(&tx)) {
		(void)k_sem_take(&link_wake, K_MSEC(50));
	}
	marker_off(MARKER_TX);   /* already LOW; keeps the invariant if the binding changes */

	/* D3 WAIT: until the response of this request_id is parsed. */
	marker_on(MARKER_WAIT);
	const uint32_t t5 = ble_cycle_now();
	r->tx_cycles = t5 - t4;
	r->att_mtu = tx.att_mtu;
	r->fragments = tx.fragments;
	r->enomem_retries = tx.enomem_retries;
	enum ble_error error = BLE_OK;
	if (tx.status != LINK_TX_DONE) {
		error = tx.status == LINK_TX_NOTCONN ? BLE_E_DISCONNECT : BLE_E_TX;
	} else {
		const uint32_t deadline = k_uptime_get_32() + CONFIG_WEEK10_RESPONSE_TIMEOUT_MS;
		for (;;) {
			const uint8_t *frame;
			uint16_t length;
			uint8_t stream;
			if (link_rx_take(&frame, &length, &stream)) {
				struct i1v2_response response;
				const int drop = i1v2_parse_response(frame, length, r->request_id,
								     FRAG_MAX_FRAME, &response);
				link_rx_release();
				if (drop != 0 || stream != FRAG_STREAM_I1) {
					r->invalid_responses++;
					continue;
				}
				r->response_status = response.status;
				memcpy(r->logits, response.logits, sizeof(r->logits));
				error = response.status == I1_OK ? BLE_OK : BLE_E_ERROR_RESPONSE;
				break;
			}
			if (link_disconnections() != disconnections) {
				error = BLE_E_DISCONNECT;
				break;
			}
			const uint32_t now = k_uptime_get_32();
			if ((int32_t)(now - deadline) >= 0) {
				error = BLE_E_TIMEOUT;
				break;
			}
			link_rx_tick(now);
			(void)k_sem_take(&link_wake, K_MSEC(MIN(deadline - now, 50u)));
		}
	}
	const uint32_t t6 = ble_cycle_now();
	marker_off(MARKER_WAIT);
	r->wait_cycles = t6 - t5;
	return error;
}

static void run_entry(unsigned cycle, unsigned split, unsigned sample, uint8_t rho, uint8_t k,
		      uint16_t payload_req, struct ble_result *r)
{
	memset(r, 0, sizeof(*r));
	r->cycle = cycle;
	r->split = split;
	r->rho = rho;
	r->k = k;
	r->payload_req = payload_req;
	r->device_only = split == BLE_DEVICE_ONLY_SPLIT;
	r->label = G2_NO_LABEL;

	/* D4 CTRL: stub controller (week 15-17 replaces it). The pad keeps the pulse visible. */
	marker_ctrl_on();
	const uint32_t t0 = ble_cycle_now();
	r->sample = sample;
	/* Week 10 firmware knows rho0, link state 0 and the natural payload only (W10-D4). */
	const bool valid = split < BLE_SPLITS && rho == 0u && k == 0u && payload_req == 0u;
	while (ble_cycle_now() - t0 < (uint32_t)CONFIG_WEEK10_CTRL_MIN_US * (CPU_HZ / 1000000u)) {
	}
	const uint32_t t1 = ble_cycle_now();
	marker_ctrl_off();
	r->ctrl_cycles = t1 - t0;
	if (!valid) {
		r->error = BLE_E_ARGUMENT;
		return;
	}

	/* D0 HEAD: head(s) + quantization. */
	marker_on(MARKER_HEAD);
	struct ble_tensor tensor;
	const int head = ble_head(r->split, r->sample, &tensor, NULL);
	const uint32_t t2 = ble_cycle_now();
	marker_off(MARKER_HEAD);
	r->head_cycles = t2 - t1;
	r->quant_cycles = last_quant_cycles;
	if (head != 0) {
		r->error = head == -3 ? BLE_E_ARGUMENT : head == -2 ? BLE_E_QUANT : BLE_E_HEAD;
		return;
	}
	r->bytes_payload = (uint32_t)tensor.channels * tensor.length + 2u * tensor.channels;

	if (r->device_only) {
		/* s10: the head output is the 5 FP32 logits of the full model. */
		memcpy(r->logits, tensor.values, sizeof(r->logits));
		r->error = BLE_OK;
	} else {
		r->error = exchange(&tensor, r);
	}
	/* Label on the dongle, after the last phase so no phase includes it. */
	if (r->error == BLE_OK) {
		r->label = g2_label(r->logits);
	}
}

void ble_cycle_run_plan(unsigned cycle, struct ble_result *r)
{
	if (cycle >= WEEK10_BLE_PLAN_CYCLES) {
		run_entry(cycle, BLE_SPLITS, 0u, 0u, 0u, 0u, r);
		return;
	}
	const struct week10_ble_entry *e = &week10_ble_plan[cycle];
	run_entry(cycle, e->split, ble_plan_sample(cycle), e->rho, e->k, e->payload_bytes, r);
}

void ble_cycle_run(unsigned split, unsigned sample, struct ble_result *r)
{
	run_entry(0u, split, sample, 0u, 0u, 0u, r);
}
