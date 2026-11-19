/* Host shim for check_week10.py and test_week10_host.py: the W8-D3 inputs (week8_inputs.h) through the
 * week 7 fast head and the week 5 quantizer exactly as ble_cycle.c ble_head() does (q/scale of any s,
 * and the FP32 head output: at s10 the 5 logits the dongle labels), and the W10-D4 plan digest computed
 * with ble_plan_bytes.h + week 6 SHA-256, as ble_plan_digest() does on the dongle. */
#include <stdint.h>
#include <string.h>

#include "ble_plan_bytes.h"
#include "g2_plan.h"
#include "head_fast.h"
#include "quantization.h"
#include "sha256.h"
#include "week8_inputs.h"

#if defined(_WIN32)
#define SHIM_EXPORT __declspec(dllexport)
#else
#define SHIM_EXPORT
#endif

SHIM_EXPORT const char *shim_set_sha256(void)
{
	return WEEK8_SET_SHA256;
}

/* FP32 head output of sample n at split (count values), 0 or negative on error. */
SHIM_EXPORT int shim_head_values(unsigned n, unsigned split, float *out, unsigned capacity, unsigned *count)
{
	struct week4_result result;
	if (n >= WEEK8_SAMPLE_COUNT || head_fast_run(split, week8_inputs[n], &result) != 0 ||
	    result.shape.count > capacity) {
		return -1;
	}
	memcpy(out, result.values, result.shape.count * sizeof(float));
	*count = result.shape.count;
	return 0;
}

/* q (C*L bytes) and FP16 LE scales (2*C bytes) of sample n at split, as ble_head(). */
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

/* g2_label() of week8/g2_plan.h (the dongle's label rule). */
SHIM_EXPORT int shim_label(const float *logits)
{
	return g2_label(logits);
}

SHIM_EXPORT unsigned shim_plan_cycles(void)
{
	return WEEK10_BLE_PLAN_CYCLES;
}

SHIM_EXPORT const char *shim_plan_sha256(void)
{
	return WEEK10_BLE_PLAN_SHA256;
}

SHIM_EXPORT void shim_plan_digest(char out[65])
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
