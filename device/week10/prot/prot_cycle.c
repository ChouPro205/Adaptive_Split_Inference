/* See prot_cycle.h. Fork of week9/dev_cycle.c (hash-locked: head + quantization, CTRL/HEAD body) with the D1
 * PROT phase of week8/g2_cycle.c (hash-locked: nonce from the reserved block, descriptor, protect). */
#include "prot_cycle.h"

#include <string.h>

#include <cmsis_core.h>
#include <zephyr/kernel.h>

#include "head_fast.h"
#include "marker_ctrl.h"
#include "markers.h"
#include "nonce_nvs.h"
#include "packets.h"
#include "quantization.h"
#include "sha256.h"
/* The only translation unit that includes the generated set (100 x 360 FP32 = 144 000 B) and plan. */
#include "week8_inputs.h"
#include "week10_prot_plan.h"

#define CPU_HZ 64000000u
#define WIRE_SPLIT_BASE 256u   /* registry: wire_split_id = 256 + s */

BUILD_ASSERT(WEEK4_SPLIT_COUNT == PROT_HEAD_SPLITS, "R3 mapping limits differ");
BUILD_ASSERT(WEEK8_SAMPLE_COUNT == 100U, "W8-D3: 100 samples");
BUILD_ASSERT(WEEK10_PROT_PLAN_ROUNDS <= WEEK8_SAMPLE_COUNT, "round k uses W8-D3 sample k");
BUILD_ASSERT(WEEK10_PROT_PLAN_CYCLES == WEEK10_PROT_PLAN_ROUNDS * WEEK10_PROT_CYCLES_PER_ROUND, "plan size");
BUILD_ASSERT(WEEK10_PROT_CYCLES_PER_ROUND == 2u * PROT_SPLITS + 1u, "W10-D1: 10 pairs + 1 HEAD-only s1");
BUILD_ASSERT(WEEK10_OP_P0 == PROT_OP_P0 && WEEK10_OP_P1 == PROT_OP_P1 && WEEK10_OP_CONV == PROT_OP_CONV, "ops");
/* One reservation block per boot (W7-D2: no Flash write inside a cycle): the boot spends one sequence on the
 * reservation, the P1 cycles of the session (one per pair) take the rest. */
BUILD_ASSERT(WEEK10_PROT_PLAN_ROUNDS * PROT_SPLITS < NONCE_RESERVE_BLOCK, "P1 cycles must fit one nonce block");
BUILD_ASSERT(PROT_MAX_VALUES <= PKT_MAX_PAYLOAD && PROT_MAX_CHANNELS <= PKT_MAX_CHANNELS, "I2 profile limits");

/* Kept in every image (check_week10_build.py), also without a console. */
static const char set_tag[] = "WEEK10_SET_SHA256=" WEEK8_SET_SHA256;
static const char plan_tag[] = "WEEK10_PROT_PLAN_SHA256=" WEEK10_PROT_PLAN_SHA256;

const char *const prot_error_names[PROT_E_COUNT] = {"OK", "ARGUMENT", "HEAD", "QUANT", "NONCE", "PROTECT"};
const char *const prot_op_names[PROT_OP_COUNT] = {"P0", "P1", "CONV"};

static int8_t q_buf[PROT_MAX_VALUES];
static uint8_t scale_le_buf[2u * PROT_MAX_CHANNELS];
static uint32_t scale_bits_buf[PROT_MAX_CHANNELS];
static uint8_t transformed[PROT_MAX_VALUES];
static uint32_t last_quant_cycles;

/* nonce_nvs.c (week 6) times its Flash writes with link_cycles() of week 6 ble_link.c; this image has no
 * radio, so the same DWT counter is provided here. */
uint32_t link_cycles(void)
{
	return DWT->CYCCNT;
}

unsigned prot_sample_count(void)
{
	return WEEK10_PROT_PLAN_ROUNDS;
}

const char *prot_sample_id(unsigned sample)
{
	return sample < WEEK8_SAMPLE_COUNT ? week8_sample_ids[sample] : "?";
}

const char *prot_set_sha256(void)
{
	return WEEK8_SET_SHA256;
}

unsigned prot_plan_cycles(void)
{
	return WEEK10_PROT_PLAN_CYCLES;
}

unsigned prot_plan_split(unsigned cycle)
{
	return cycle < WEEK10_PROT_PLAN_CYCLES ? week10_prot_plan[cycle][0] : PROT_HEAD_SPLITS;
}

enum prot_op prot_plan_op(unsigned cycle)
{
	return cycle < WEEK10_PROT_PLAN_CYCLES ? (enum prot_op)week10_prot_plan[cycle][1] : PROT_OP_COUNT;
}

unsigned prot_plan_sample(unsigned cycle)
{
	return cycle / WEEK10_PROT_CYCLES_PER_ROUND;
}

unsigned prot_plan_p1_cycles(unsigned first, unsigned count)
{
	unsigned n = 0;
	for (unsigned i = first; i < first + count && i < WEEK10_PROT_PLAN_CYCLES; ++i) {
		n += week10_prot_plan[i][1] == WEEK10_OP_P1;
	}
	return n;
}

const char *prot_plan_sha256(void)
{
	return WEEK10_PROT_PLAN_SHA256;
}

void prot_plan_digest(char out[65])
{
	uint8_t digest[32];
	sha256(&week10_prot_plan[0][0], sizeof(week10_prot_plan), digest);
	sha256_hex(digest, out);
}

uint32_t prot_cycle_now(void)
{
	__asm__ volatile("" ::: "memory");
	const uint32_t cycles = DWT->CYCCNT;
	__asm__ volatile("" ::: "memory");
	return cycles;
}

uint32_t prot_last_quant_cycles(void)
{
	return last_quant_cycles;
}

uint16_t prot_wire_split_id(unsigned split)
{
	return (uint16_t)(WIRE_SPLIT_BASE + split);
}

int prot_head(unsigned split, unsigned sample, struct prot_tensor *out, uint32_t *head_cycles)
{
	struct week4_result result;
	if (sample >= WEEK8_SAMPLE_COUNT || split >= WEEK4_SPLIT_COUNT) {
		return -3;
	}
	const uint32_t h0 = prot_cycle_now();
	int status = head_fast_run(split, week8_inputs[sample], &result);
	const uint32_t c0 = prot_cycle_now();
	if (head_cycles != NULL) {
		*head_cycles = c0 - h0;
	}
	if (status != 0) {
		return -1;
	}
	const unsigned channels = result.shape.dims[1];
	const unsigned length = result.shape.rank == 3U ? result.shape.dims[2] : 1U;
	if (channels > PROT_MAX_CHANNELS || result.shape.count > PROT_MAX_VALUES ||
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
	last_quant_cycles = prot_cycle_now() - c0;
	*out = (struct prot_tensor){split, sample, (uint16_t)channels, length, q_buf, scale_le_buf, scale_bits_buf};
	return 0;
}

int prot_conv(unsigned sample, const float **values, unsigned *count)
{
	struct week4_result result;
	if (sample >= WEEK8_SAMPLE_COUNT || head_fast_run(PROT_CONV_SPLIT, week8_inputs[sample], &result) != 0) {
		return -1;
	}
	*values = result.values;
	*count = result.shape.count;
	return 0;
}

static struct pkt_tensor packet_tensor(const struct prot_tensor *t)
{
	return (struct pkt_tensor){PKT_MODEL_PROFILE_ID, prot_wire_split_id(t->split), t->channels, t->length,
				   t->q, t->scale_bits};
}

i2_status prot_protect(const struct prot_tensor *t, const uint8_t *key, const uint8_t nonce[12], uint8_t *out,
		       size_t capacity, uint32_t *cycles)
{
	const struct pkt_tensor pt = packet_tensor(t);
	uint8_t descriptor[I2_DESCRIPTOR_BYTES];
	const uint32_t c0 = prot_cycle_now();
	i2_status status = pkt_descriptor(&pt, PKT_KEY_ID, descriptor);
	if (status == I2_OK) {
		status = pkt_protect(&pt, PKT_KEY_ID, key, nonce, descriptor, out, capacity);
	}
	*cycles = prot_cycle_now() - c0;
	return status;
}

void prot_cycle_init(void)
{
	/* W8-D4 labels are for s=2 only and are not used in week 10. */
	(void)week8_reference_labels;
	__asm__ volatile("" : : "r"(set_tag), "r"(plan_tag) : "memory");
}

static void run_entry(unsigned cycle, unsigned split, unsigned sample, enum prot_op op, struct prot_result *r)
{
	memset(r, 0, sizeof(*r));
	r->cycle = cycle;
	r->split = split;
	r->op = op;
	const uint32_t writes_before = nonce_nvs_storage_writes();

	/* D4 CTRL: stub controller (week 15-17 replaces it). The pad keeps the pulse visible. */
	marker_ctrl_on();
	const uint32_t t0 = prot_cycle_now();
	r->sample = sample;
	const bool valid = op < PROT_OP_COUNT && (op == PROT_OP_CONV ? split == PROT_CONV_SPLIT : split < PROT_SPLITS);
	while (prot_cycle_now() - t0 < (uint32_t)CONFIG_WEEK10_CTRL_MIN_US * (CPU_HZ / 1000000u)) {
	}
	const uint32_t t1 = prot_cycle_now();
	marker_ctrl_off();
	r->ctrl_cycles = t1 - t0;
	if (!valid) {
		r->error = PROT_E_ARGUMENT;
		return;
	}

	/* D0 HEAD: head(s) + quantization, or head(s1) only for the conv cycle. */
	marker_on(MARKER_HEAD);
	struct prot_tensor tensor;
	int head;
	if (op == PROT_OP_CONV) {
		const float *values;
		unsigned count;
		head = prot_conv(r->sample, &values, &count);
	} else {
		head = prot_head(r->split, r->sample, &tensor, NULL);
	}
	const uint32_t t2 = prot_cycle_now();
	marker_off(MARKER_HEAD);
	r->head_cycles = t2 - t1;
	if (head != 0) {
		r->error = head == -3 ? PROT_E_ARGUMENT : head == -2 ? PROT_E_QUANT : PROT_E_HEAD;
		return;
	}
	if (op == PROT_OP_CONV) {
		r->error = PROT_OK;
		r->nonce_writes = nonce_nvs_storage_writes() - writes_before;
		return;
	}
	r->quant_cycles = last_quant_cycles;
	r->bytes_payload = (uint32_t)tensor.channels * tensor.length + 2u * tensor.channels;

	/* D1 PROT (P1 only): nonce + descriptor + protect, the week 8 phase. */
	enum prot_error error = PROT_OK;
	if (op == PROT_OP_P1) {
		const struct pkt_tensor pt = packet_tensor(&tensor);
		uint8_t descriptor[I2_DESCRIPTOR_BYTES], nonce[I2_NONCE_BYTES];
		marker_on(MARKER_PROTECTION);
		const uint32_t c0 = prot_cycle_now();
		const uint8_t *key = nonce_nvs_key();
		if (key == NULL || nonce_nvs_allocate(&r->sequence, nonce) != 0) {
			error = PROT_E_NONCE;
		} else if (pkt_descriptor(&pt, PKT_KEY_ID, descriptor) != I2_OK ||
			   pkt_protect(&pt, PKT_KEY_ID, key, nonce, descriptor, transformed,
				       sizeof(transformed)) != I2_OK) {
			error = PROT_E_PROTECT;
		}
		r->prot_cycles = prot_cycle_now() - c0;
		marker_off(MARKER_PROTECTION);
#if defined(CONFIG_WEEK10_PROT_USB)
		if (error == PROT_OK) {
			sha256(transformed, (size_t)tensor.channels * tensor.length, r->digest);
		}
#endif
	}
	r->nonce_writes = nonce_nvs_storage_writes() - writes_before;
	r->error = error;
}

void prot_cycle_run_plan(unsigned cycle, struct prot_result *r)
{
	run_entry(cycle, prot_plan_split(cycle), prot_plan_sample(cycle), prot_plan_op(cycle), r);
}

void prot_cycle_run(unsigned split, unsigned sample, enum prot_op op, struct prot_result *r)
{
	run_entry(0u, split, sample, op, r);
}
