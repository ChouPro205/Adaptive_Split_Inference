/* Host shim for test_week11_s0c_host.py: s0c_encode() of device/week11/s0c.c exported flat, so ctypes can
 * compare it with contracts/s0c_v1_ref/s0c_v1_ref.py and the golden set. Same sources as the firmware. */
#include <stdint.h>
#include <string.h>

#include "s0c.h"

#if defined(_WIN32)
#define SHIM_EXPORT __declspec(dllexport)
#else
#define SHIM_EXPORT
#endif

SHIM_EXPORT unsigned shim_body_max(void)
{
	return S0C_BODY_MAX;
}

/* x: 360 FP32; outputs: reduced (46 FP32), q (46), scale_le (2), body (S0C_BODY_MAX), *body_len, *k. */
SHIM_EXPORT int shim_s0c_encode(const float *x, float *reduced, int8_t *q, uint8_t *scale_le, uint8_t *body,
				unsigned *body_len, unsigned *k)
{
	struct s0c_beat beat;
	const int status = s0c_encode(x, &beat);
	if (status != S0C_OK) {
		return status;
	}
	memcpy(reduced, beat.reduced, sizeof(beat.reduced));
	memcpy(q, beat.q, sizeof(beat.q));
	memcpy(scale_le, beat.scale_le, sizeof(beat.scale_le));
	memcpy(body, beat.body, sizeof(beat.body));
	*body_len = beat.body_len;
	*k = beat.k;
	return S0C_OK;
}

#if defined(S0C_SHIM_WEEK8)
/* The W8-D3 inputs the firmware encodes (week8_inputs.h of the build, -I <samples dir>). */
#include "week8_inputs.h"

SHIM_EXPORT const char *shim_set_sha256(void)
{
	return WEEK8_SET_SHA256;
}

SHIM_EXPORT int shim_week8_input(unsigned n, float *x)
{
	if (n >= WEEK8_SAMPLE_COUNT) {
		return -1;
	}
	(void)week8_sample_ids;
	(void)week8_reference_labels;
	memcpy(x, week8_inputs[n], sizeof(week8_inputs[n]));
	return 0;
}
#endif
