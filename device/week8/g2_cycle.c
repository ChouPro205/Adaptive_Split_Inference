/* See g2_cycle.h. Fork of week7/energy_cycle.c (hash-locked); the cycle body is unchanged. */
#include "g2_cycle.h"

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
#include "nonce_nvs.h"
#include "quantization.h"
/* The only translation unit that includes the generated set (100 x 360 FP32 = 144 000 B). */
#include "week8_inputs.h"

#define CPU_HZ 64000000u
#define WIRE_SPLIT_BASE 256u   /* registry mitdb-week5-i2-registry-v1-r1: wire_split_id = 256 + s */

BUILD_ASSERT(WEEK4_SPLIT_COUNT == 11U, "R3 mapping limits differ");
BUILD_ASSERT(WEEK8_SAMPLE_COUNT == 100U, "W8-D3: 100 samples");
/* The inputs and reference labels of week8_inputs.h are for one split only. */
BUILD_ASSERT(CONFIG_WEEK7_SPLIT == WEEK8_SPLIT, "week8_inputs.h was generated for another split");
/* One reservation block per boot (W7-D2: no Flash write inside a cycle): the session reserves
 * it before the self-test and spends one sequence on that, leaving 1023 for the P1 cycles. */
BUILD_ASSERT(CONFIG_WEEK8_PAIRS < NONCE_RESERVE_BLOCK, "P1 cycles (one per pair) must fit one nonce block");

/* Kept in every image (check_week8_build.py: set_sha256_in_image), also without a console. */
static const char set_tag[] = "WEEK8_SET_SHA256=" WEEK8_SET_SHA256;

const char *const cycle_error_names[CYCLE_E_COUNT] = {
	"OK", "HEAD", "QUANT", "NONCE", "PROTECT", "ENCODE", "NOT_READY", "TX", "TIMEOUT",
	"DISCONNECT", "ERROR_RESPONSE",
};

static int8_t q_buf[PKT_MAX_PAYLOAD];
static uint8_t scale_le_buf[2u * PKT_MAX_CHANNELS];
static uint32_t scale_bits_buf[PKT_MAX_CHANNELS];
static uint8_t transformed[PKT_MAX_PAYLOAD];
static uint8_t tx_frame[FRAG_MAX_FRAME];
static uint32_t last_request_id;
static uint32_t last_quant_cycles;

unsigned g2_sample_count(void)
{
	return WEEK8_SAMPLE_COUNT;
}

const char *g2_sample_id(unsigned sample)
{
	return sample < WEEK8_SAMPLE_COUNT ? week8_sample_ids[sample] : "?";
}

uint8_t g2_reference_label(unsigned sample)
{
	return sample < WEEK8_SAMPLE_COUNT ? week8_reference_labels[sample] : G2_NO_LABEL;
}

const char *g2_set_sha256(void)
{
	return WEEK8_SET_SHA256;
}

uint32_t g2_cycle_now(void)
{
	__asm__ volatile("" ::: "memory");
	const uint32_t cycles = DWT->CYCCNT;
	__asm__ volatile("" ::: "memory");
	return cycles;
}

uint16_t pipeline_wire_split_id(unsigned split)
{
	return (uint16_t)(WIRE_SPLIT_BASE + split);
}

int pipeline_head(unsigned split, unsigned sample, struct pipeline_tensor *out)
{
	struct week4_result result;
	if (sample >= WEEK8_SAMPLE_COUNT) {
		return -1;
	}
#if defined(CONFIG_WEEK7_KERNEL_FAST)
	int status = head_fast_run(split, week8_inputs[sample], &result);
#else
	int status = week4_run_head(split, week8_inputs[sample], &result);
#endif
	if (status != 0) {
		return -1;
	}
	const unsigned channels = result.shape.dims[1];
	const unsigned length = result.shape.rank == 3U ? result.shape.dims[2] : 1U;
	if (channels > PKT_MAX_CHANNELS || result.shape.count > PKT_MAX_PAYLOAD ||
	    channels * length != result.shape.count) {
		return -1;
	}
	const uint32_t c0 = g2_cycle_now();
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
	last_quant_cycles = g2_cycle_now() - c0;
	*out = (struct pipeline_tensor){split, sample, (uint16_t)channels, length, q_buf,
					scale_le_buf, scale_bits_buf};
	return 0;
}

static struct pkt_tensor packet_tensor(const struct pipeline_tensor *t)
{
	return (struct pkt_tensor){PKT_MODEL_PROFILE_ID, pipeline_wire_split_id(t->split),
				   t->channels, t->length, t->q, t->scale_bits};
}

size_t pipeline_request(const struct pipeline_tensor *t, uint32_t request_id, const uint8_t *key,
			const uint8_t nonce[12], uint8_t *frame, uint32_t *prot_cycles)
{
	const struct pkt_tensor pt = packet_tensor(t);
	const uint8_t *payload = (const uint8_t *)t->q;
	uint8_t descriptor[I2_DESCRIPTOR_BYTES];
	*prot_cycles = 0;
	if (key != NULL) {
		if (pkt_descriptor(&pt, PKT_KEY_ID, descriptor) != I2_OK) {
			return 0;
		}
		const uint32_t c0 = g2_cycle_now();
		if (pkt_protect(&pt, PKT_KEY_ID, key, nonce, descriptor, transformed,
				sizeof(transformed)) != I2_OK) {
			return 0;
		}
		*prot_cycles = g2_cycle_now() - c0;
		payload = transformed;
	}
	return pkt_encode(frame, FRAG_MAX_FRAME, request_id, &pt, payload,
			  key != NULL ? descriptor : NULL, key != NULL ? nonce : NULL);
}

void g2_cycle_init(void)
{
	__asm__ volatile("" : : "r"(set_tag) : "memory");
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

void g2_cycle_run(unsigned sample, bool p1, struct cycle_result *r)
{
	memset(r, 0, sizeof(*r));
	r->p1 = p1;
	r->split = CONFIG_WEEK7_SPLIT;
	r->label = G2_NO_LABEL;
	const uint32_t writes_before = nonce_nvs_storage_writes();

	/* D4 CTRL: stub controller (week 15-17 replaces it). The pad keeps the pulse visible. */
	marker_ctrl_on();
	const uint32_t t0 = g2_cycle_now();
	r->sample = sample;
	while (g2_cycle_now() - t0 < (uint32_t)CONFIG_WEEK7_CTRL_MIN_US * (CPU_HZ / 1000000u)) {
	}
	const uint32_t t1 = g2_cycle_now();
	marker_ctrl_off();

	/* D0 HEAD: head(s) + quantization. */
	marker_on(MARKER_HEAD);
	struct pipeline_tensor tensor;
	const int head = pipeline_head(r->split, r->sample, &tensor);
	const uint32_t t2 = g2_cycle_now();
	marker_off(MARKER_HEAD);
	r->ctrl_cycles = t1 - t0;
	r->head_cycles = t2 - t1;
	r->quant_cycles = last_quant_cycles;
	if (head != 0) {
		r->error = head == -2 ? CYCLE_E_QUANT : CYCLE_E_HEAD;
		return;
	}

	/* D1 PROT (P1 only): nonce + descriptor + protect. */
	const struct pkt_tensor pt = packet_tensor(&tensor);
	const uint8_t *payload = (const uint8_t *)tensor.q;
	uint8_t descriptor[I2_DESCRIPTOR_BYTES], nonce[I2_NONCE_BYTES];
	if (p1) {
		marker_on(MARKER_PROTECTION);
		const uint32_t c0 = g2_cycle_now();
		const uint8_t *key = nonce_nvs_key();
		enum cycle_error error = CYCLE_OK;
		if (key == NULL || nonce_nvs_allocate(&r->sequence, nonce) != 0) {
			error = CYCLE_E_NONCE;
		} else if (pkt_descriptor(&pt, PKT_KEY_ID, descriptor) != I2_OK ||
			   pkt_protect(&pt, PKT_KEY_ID, key, nonce, descriptor, transformed,
				       sizeof(transformed)) != I2_OK) {
			error = CYCLE_E_PROTECT;
		}
		r->prot_cycles = g2_cycle_now() - c0;
		marker_off(MARKER_PROTECTION);
		if (error != CYCLE_OK) {
			r->error = error;
			return;
		}
		payload = transformed;
	}

	/* D2 TX: encode + CRC + fragments; the sender thread clears D2 after the last completion. */
	marker_on(MARKER_TX);
	const uint32_t t4 = g2_cycle_now();
	r->request_id = pkt_next_request_id(&last_request_id);
	r->frame_length = pkt_encode(tx_frame, sizeof(tx_frame), r->request_id, &pt, payload,
				     p1 ? descriptor : NULL, p1 ? nonce : NULL);
	r->encode_cycles = g2_cycle_now() - t4;
	if (r->frame_length == 0u) {
		marker_off(MARKER_TX);
		r->error = CYCLE_E_ENCODE;
		return;
	}
	if (!link_ready()) {
		marker_off(MARKER_TX);
		r->error = CYCLE_E_NOT_READY;
		return;
	}
	drop_stale_frames();
	const uint32_t disconnections = link_disconnections();
	if (link_send(tx_frame, (uint16_t)r->frame_length, FRAG_STREAM_I1) != 0) {
		marker_off(MARKER_TX);
		r->error = CYCLE_E_TX;
		return;
	}
	struct link_tx_result tx;
	while (!link_tx_take_result(&tx)) {
		(void)k_sem_take(&link_wake, K_MSEC(50));
	}
	marker_off(MARKER_TX);   /* already LOW; keeps the invariant if the binding changes */

	/* D3 WAIT: until the response of this request_id is parsed. */
	marker_on(MARKER_WAIT);
	const uint32_t t5 = g2_cycle_now();
	r->tx_cycles = t5 - t4;
	r->att_mtu = tx.att_mtu;
	r->fragments = tx.fragments;
	r->enomem_retries = tx.enomem_retries;
	enum cycle_error error = CYCLE_OK;
	if (tx.status != LINK_TX_DONE) {
		error = tx.status == LINK_TX_NOTCONN ? CYCLE_E_DISCONNECT : CYCLE_E_TX;
	} else {
		const uint32_t deadline = k_uptime_get_32() + CONFIG_WEEK7_RESPONSE_TIMEOUT_MS;
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
				error = response.status == I1_OK ? CYCLE_OK : CYCLE_E_ERROR_RESPONSE;
				break;
			}
			if (link_disconnections() != disconnections) {
				error = CYCLE_E_DISCONNECT;
				break;
			}
			const uint32_t now = k_uptime_get_32();
			if ((int32_t)(now - deadline) >= 0) {
				error = CYCLE_E_TIMEOUT;
				break;
			}
			link_rx_tick(now);
			(void)k_sem_take(&link_wake, K_MSEC(MIN(deadline - now, 50u)));
		}
	}
	const uint32_t t6 = g2_cycle_now();
	marker_off(MARKER_WAIT);
	r->wait_cycles = t6 - t5;
	r->nonce_writes = nonce_nvs_storage_writes() - writes_before;
	r->error = error;
	/* Label on the dongle (G2 criterion), after D3 so no phase includes it. */
	if (error == CYCLE_OK) {
		r->label = g2_label(r->logits);
	}
}
