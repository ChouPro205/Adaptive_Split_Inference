/* Host shim for test_week8_host.py: the generated week8_inputs.h through the week 7 fast head and
 * the week 5 quantizer exactly as g2_cycle.c pipeline_head() does, plus the g2_plan.h rules. */
#include <stdint.h>
#include <string.h>

#include "g2_plan.h"
#include "head_fast.h"
#include "quantization.h"
#include "week8_inputs.h"

#if defined(_WIN32)
#define SHIM_EXPORT __declspec(dllexport)
#else
#define SHIM_EXPORT
#endif

SHIM_EXPORT unsigned shim_sample_count(void)
{
	return WEEK8_SAMPLE_COUNT;
}

SHIM_EXPORT unsigned shim_split(void)
{
	return WEEK8_SPLIT;
}

SHIM_EXPORT const char *shim_set_sha256(void)
{
	return WEEK8_SET_SHA256;
}

SHIM_EXPORT const char *shim_sample_id(unsigned n)
{
	return n < WEEK8_SAMPLE_COUNT ? week8_sample_ids[n] : NULL;
}

SHIM_EXPORT int shim_reference_label(unsigned n)
{
	return n < WEEK8_SAMPLE_COUNT ? week8_reference_labels[n] : -1;
}

SHIM_EXPORT const float *shim_inputs(void)
{
	return &week8_inputs[0][0];
}

/* q (C*L bytes) and FP16 LE scales (2*C bytes) of sample n at WEEK8_SPLIT; channels/length out.
 * Returns 0, or a negative value on invalid arguments or a failed step. */
SHIM_EXPORT int shim_head_quant(unsigned n, int8_t *q, unsigned q_capacity, uint8_t *scale_le,
				unsigned scale_capacity, unsigned *channels, unsigned *length)
{
	struct week4_result result;
	if (n >= WEEK8_SAMPLE_COUNT || head_fast_run(WEEK8_SPLIT, week8_inputs[n], &result) != 0) {
		return -1;
	}
	const unsigned c = result.shape.dims[1];
	const unsigned l = result.shape.rank == 3U ? result.shape.dims[2] : 1U;
	if (c * l != result.shape.count) {
		return -1;
	}
	if (week5_quantize(result.values, result.shape.count, 1, c, l, q, q_capacity, scale_le,
			   scale_capacity) != WEEK5_OK) {
		return -2;
	}
	*channels = c;
	*length = l;
	return 0;
}

SHIM_EXPORT unsigned shim_pair_sample(unsigned pair, unsigned count)
{
	return g2_pair_sample(pair, count);
}

SHIM_EXPORT int shim_slot_is_p1(unsigned pair, unsigned slot)
{
	return g2_slot_is_p1(pair, slot);
}

SHIM_EXPORT int shim_label(const float *logits)
{
	return g2_label(logits);
}
