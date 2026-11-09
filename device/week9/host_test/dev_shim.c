/* Host shim for generate_week9_refs.py and test_week9_host.py: the W8-D3 inputs (week8_inputs.h)
 * through the week 7 fast head and the week 5 quantizer exactly as dev_cycle.c dev_head() does,
 * at any split. With -DWEEK9_SHIM_PLAN it also exposes the generated week9_plan.h. */
#include <stdint.h>
#include <string.h>

#include "head_fast.h"
#include "quantization.h"
#include "week8_inputs.h"
#if defined(WEEK9_SHIM_PLAN)
#include "week9_plan.h"
#endif

#if defined(_WIN32)
#define SHIM_EXPORT __declspec(dllexport)
#else
#define SHIM_EXPORT
#endif

SHIM_EXPORT unsigned shim_sample_count(void)
{
	return WEEK8_SAMPLE_COUNT;
}

SHIM_EXPORT const char *shim_set_sha256(void)
{
	return WEEK8_SET_SHA256;
}

SHIM_EXPORT const char *shim_sample_id(unsigned n)
{
	return n < WEEK8_SAMPLE_COUNT ? week8_sample_ids[n] : NULL;
}

/* W8-D4 labels are for s=2 only; exported so the header is used whole (week 9 does not use them). */
SHIM_EXPORT int shim_reference_label_s2(unsigned n)
{
	return n < WEEK8_SAMPLE_COUNT ? week8_reference_labels[n] : -1;
}

/* q (C*L bytes) and FP16 LE scales (2*C bytes) of sample n at split; channels/length out.
 * Returns 0, or a negative value on invalid arguments or a failed step. */
SHIM_EXPORT int shim_head_quant(unsigned n, unsigned split, int8_t *q, unsigned q_capacity,
				uint8_t *scale_le, unsigned scale_capacity, unsigned *channels,
				unsigned *length)
{
	struct week4_result result;
	if (n >= WEEK8_SAMPLE_COUNT || head_fast_run(split, week8_inputs[n], &result) != 0) {
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

#if defined(WEEK9_SHIM_PLAN)
SHIM_EXPORT unsigned shim_plan_cycles(void)
{
	return WEEK9_PLAN_CYCLES;
}

SHIM_EXPORT unsigned shim_plan_rounds(void)
{
	return WEEK9_PLAN_ROUNDS;
}

SHIM_EXPORT unsigned shim_plan_seed(void)
{
	return WEEK9_PLAN_SEED;
}

SHIM_EXPORT const char *shim_plan_sha256(void)
{
	return WEEK9_PLAN_SHA256;
}

SHIM_EXPORT const uint8_t *shim_plan_splits(void)
{
	return week9_plan_split;
}
#endif
