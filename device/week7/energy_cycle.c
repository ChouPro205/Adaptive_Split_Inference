/* See energy_cycle.h. */
#include "energy_cycle.h"

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
#include "week4_inputs.h"

#define CPU_HZ 64000000u
#define WIRE_SPLIT_BASE 256u   /* registry mitdb-week5-i2-registry-v1-r1: wire_split_id = 256 + s */

BUILD_ASSERT(WEEK4_SAMPLE_COUNT == 20U && WEEK4_SPLIT_COUNT == 11U, "R3 mapping limits differ");
BUILD_ASSERT(CONFIG_WEEK7_SPLIT < WEEK4_SPLIT_COUNT, "split out of range");
/* One reservation block per boot (W7-D2: no Flash write inside a cycle): the session reserves
 * it before the self-test and spends one sequence on that, leaving 1023 for the P1 cycles. */
BUILD_ASSERT(CONFIG_WEEK7_P1_CYCLES < NONCE_RESERVE_BLOCK, "P1 cycles must fit one nonce block");

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

uint32_t energy_cycle_now(void)
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
	if (sample >= WEEK4_SAMPLE_COUNT) {
		return -1;
	}
#if defined(CONFIG_WEEK7_KERNEL_FAST)
	int status = head_fast_run(split, week4_inputs[sample], &result);
#else
	int status = week4_run_head(split, week4_inputs[sample], &result);
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
	const uint32_t c0 = energy_cycle_now();
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
	last_quant_cycles = energy_cycle_now() - c0;
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
		const uint32_t c0 = energy_cycle_now();
		if (pkt_protect(&pt, PKT_KEY_ID, key, nonce, descriptor, transformed,
				sizeof(transformed)) != I2_OK) {
			return 0;
		}
		*prot_cycles = energy_cycle_now() - c0;
		payload = transformed;
	}
	return pkt_encode(frame, FRAG_MAX_FRAME, request_id, &pt, payload,
			  key != NULL ? descriptor : NULL, key != NULL ? nonce : NULL);
}

void energy_cycle_init(void)
{
	/* I1 v2 §11: request_id starts at a random non-zero value after every boot. */
	do {
		(void)sys_csrand_get(&last_request_id, sizeof(last_request_id));
	} while (last_request_id == 0u || last_request_id == UINT32_MAX);
	link_rx_configure(1U << FRAG_STREAM_I1);
}

const uint8_t *energy_cycle_frame(void)
{
	return tx_frame;
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

void energy_cycle_run(unsigned index, bool p1, struct cycle_result *r)
{
	memset(r, 0, sizeof(*r));
	r->p1 = p1;
	r->split = CONFIG_WEEK7_SPLIT;
	const uint32_t writes_before = nonce_nvs_storage_writes();

	/* D4 CTRL: stub controller (week 15-17 replaces it). The pad keeps the pulse visible. */
	marker_ctrl_on();
	const uint32_t t0 = energy_cycle_now();
	r->sample = index % WEEK4_SAMPLE_COUNT;
	while (energy_cycle_now() - t0 < (uint32_t)CONFIG_WEEK7_CTRL_MIN_US * (CPU_HZ / 1000000u)) {
	}
	const uint32_t t1 = energy_cycle_now();
	marker_ctrl_off();

	/* D0 HEAD: head(s) + quantization. */
	marker_on(MARKER_HEAD);
	struct pipeline_tensor tensor;
	const int head = pipeline_head(r->split, r->sample, &tensor);
	const uint32_t t2 = energy_cycle_now();
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
		const uint32_t c0 = energy_cycle_now();
		const uint8_t *key = nonce_nvs_key();
		enum cycle_error error = CYCLE_OK;
		if (key == NULL || nonce_nvs_allocate(&r->sequence, nonce) != 0) {
			error = CYCLE_E_NONCE;
		} else if (pkt_descriptor(&pt, PKT_KEY_ID, descriptor) != I2_OK ||
			   pkt_protect(&pt, PKT_KEY_ID, key, nonce, descriptor, transformed,
				       sizeof(transformed)) != I2_OK) {
			error = CYCLE_E_PROTECT;
		}
		r->prot_cycles = energy_cycle_now() - c0;
		marker_off(MARKER_PROTECTION);
		if (error != CYCLE_OK) {
			r->error = error;
			return;
		}
		payload = transformed;
	}

	/* D2 TX: encode + CRC + fragments; the sender thread clears D2 after the last completion. */
	marker_on(MARKER_TX);
	const uint32_t t4 = energy_cycle_now();
	r->request_id = pkt_next_request_id(&last_request_id);
	r->frame_length = pkt_encode(tx_frame, sizeof(tx_frame), r->request_id, &pt, payload,
				     p1 ? descriptor : NULL, p1 ? nonce : NULL);
	r->encode_cycles = energy_cycle_now() - t4;
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
	const uint32_t t5 = energy_cycle_now();
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
	const uint32_t t6 = energy_cycle_now();
	marker_off(MARKER_WAIT);
	r->wait_cycles = t6 - t5;
	r->nonce_writes = nonce_nvs_storage_writes() - writes_before;
	r->error = error;
}
