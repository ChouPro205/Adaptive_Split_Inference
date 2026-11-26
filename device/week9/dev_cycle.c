/* See dev_cycle.h. Fork of week8/g2_cycle.c (hash-locked): pipeline_head() and the CTRL/HEAD part
 * of g2_cycle_run() unchanged, the split is an argument instead of CONFIG_WEEK7_SPLIT. */
#include "dev_cycle.h"

#include <string.h>

#include <cmsis_core.h>
#include <zephyr/kernel.h>

#include "head_fast.h"
#include "marker_ctrl.h"
#include "markers.h"
#include "quantization.h"
#include "sha256.h"
/* The only translation unit that includes the generated set (100 x 360 FP32 = 144 000 B) and plan. */
#include "week8_inputs.h"
#include "week9_plan.h"

#define CPU_HZ 64000000u

BUILD_ASSERT(WEEK4_SPLIT_COUNT == DEV_SPLITS, "R3 mapping limits differ");
BUILD_ASSERT(WEEK8_SAMPLE_COUNT == 100U, "W8-D3: 100 samples");
BUILD_ASSERT(WEEK9_PLAN_SPLITS == WEEK4_SPLIT_COUNT, "W9-D4: every round covers every split");
BUILD_ASSERT(WEEK9_PLAN_ROUNDS <= WEEK8_SAMPLE_COUNT, "W9-D3: round k uses W8-D3 sample k");
BUILD_ASSERT(WEEK9_PLAN_CYCLES == WEEK9_PLAN_ROUNDS * WEEK9_PLAN_SPLITS, "plan size");

/* Kept in every image (check_week9_build.py), also without a console. */
static const char set_tag[] = "WEEK9_SET_SHA256=" WEEK8_SET_SHA256;
static const char plan_tag[] = "WEEK9_PLAN_SHA256=" WEEK9_PLAN_SHA256;

const char *const dev_error_names[DEV_E_COUNT] = {"OK", "ARGUMENT", "HEAD", "QUANT"};

static int8_t q_buf[DEV_MAX_VALUES];
static uint8_t scale_le_buf[2u * DEV_MAX_CHANNELS];
static uint32_t scale_bits_buf[DEV_MAX_CHANNELS];
static uint32_t last_quant_cycles;

unsigned dev_sample_count(void)
{
	return WEEK9_PLAN_ROUNDS;
}

const char *dev_sample_id(unsigned sample)
{
	return sample < WEEK8_SAMPLE_COUNT ? week8_sample_ids[sample] : "?";
}

const char *dev_set_sha256(void)
{
	return WEEK8_SET_SHA256;
}

unsigned dev_plan_cycles(void)
{
	return WEEK9_PLAN_CYCLES;
}

unsigned dev_plan_split(unsigned cycle)
{
	return cycle < WEEK9_PLAN_CYCLES ? week9_plan_split[cycle] : WEEK4_SPLIT_COUNT;
}

unsigned dev_plan_sample(unsigned cycle)
{
	return cycle / WEEK9_PLAN_SPLITS;
}

const char *dev_plan_sha256(void)
{
	return WEEK9_PLAN_SHA256;
}

void dev_plan_digest(char out[65])
{
	uint8_t digest[32];
	sha256(week9_plan_split, sizeof(week9_plan_split), digest);
	sha256_hex(digest, out);
}

uint32_t dev_cycle_now(void)
{
	__asm__ volatile("" ::: "memory");
	const uint32_t cycles = DWT->CYCCNT;
	__asm__ volatile("" ::: "memory");
	return cycles;
}

uint32_t dev_last_quant_cycles(void)
{
	return last_quant_cycles;
}

int dev_head(unsigned split, unsigned sample, struct dev_tensor *out, uint32_t *head_cycles)
{
	struct week4_result result;
	if (sample >= WEEK8_SAMPLE_COUNT || split >= WEEK4_SPLIT_COUNT) {
		return -3;
	}
	const uint32_t h0 = dev_cycle_now();
	int status = head_fast_run(split, week8_inputs[sample], &result);
	const uint32_t c0 = dev_cycle_now();
	if (head_cycles != NULL) {
		*head_cycles = c0 - h0;
	}
	if (status != 0) {
		return -1;
	}
	const unsigned channels = result.shape.dims[1];
	const unsigned length = result.shape.rank == 3U ? result.shape.dims[2] : 1U;
	if (channels > DEV_MAX_CHANNELS || result.shape.count > DEV_MAX_VALUES ||
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
	last_quant_cycles = dev_cycle_now() - c0;
	*out = (struct dev_tensor){split, sample, (uint16_t)channels, length, q_buf, scale_le_buf,
				   scale_bits_buf};
	return 0;
}

void dev_cycle_init(void)
{
	/* W8-D4 labels are for s=2 only and are not used in week 9. */
	(void)week8_reference_labels;
	__asm__ volatile("" : : "r"(set_tag), "r"(plan_tag) : "memory");
}

void dev_cycle_run(unsigned split, unsigned sample, struct dev_result *r)
{
	memset(r, 0, sizeof(*r));
	r->split = split;

	/* D4 CTRL: stub controller (week 15-17 replaces it). The pad keeps the pulse visible. */
	marker_ctrl_on();
	const uint32_t t0 = dev_cycle_now();
	r->sample = sample;
	while (dev_cycle_now() - t0 < (uint32_t)CONFIG_WEEK9_CTRL_MIN_US * (CPU_HZ / 1000000u)) {
	}
	const uint32_t t1 = dev_cycle_now();
	marker_ctrl_off();

	/* D0 HEAD: head(s) + quantization. */
	marker_on(MARKER_HEAD);
	struct dev_tensor tensor;
	const int head = dev_head(r->split, r->sample, &tensor, NULL);
	const uint32_t t2 = dev_cycle_now();
	marker_off(MARKER_HEAD);
	r->ctrl_cycles = t1 - t0;
	r->head_cycles = t2 - t1;
	r->quant_cycles = last_quant_cycles;
	if (head != 0) {
		r->error = head == -3 ? DEV_E_ARGUMENT : head == -2 ? DEV_E_QUANT : DEV_E_HEAD;
		return;
	}
	r->bytes_payload = (uint32_t)tensor.channels * tensor.length + 2u * tensor.channels;
}
