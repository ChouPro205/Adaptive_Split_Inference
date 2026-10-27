/* Host shim for generate_week8_samples.py: the week 7 fast head (bit-identical to week 4, TC7)
 * on a caller-supplied input, so the 100 week 8 samples get the q/scale the dongle computes. */
#include <stdint.h>
#include <string.h>

#include "head_fast.h"

#if defined(_WIN32)
#define SHIM_EXPORT __declspec(dllexport)
#else
#define SHIM_EXPORT
#endif

/* Copies the activation (FP32 bits) of input[360] at split to out.
 * Returns the element count, or -1 on invalid arguments. */
SHIM_EXPORT int shim_head(unsigned split, const float *input, uint32_t *out, unsigned capacity)
{
	static float copy[360];
	struct week4_result result;
	/* s=0 aliases the input; the copy also keeps the caller's buffer out of the workspace. */
	memcpy(copy, input, sizeof(copy));
	if (head_fast_run(split, copy, &result) != 0 || result.shape.count > capacity) {
		return -1;
	}
	memcpy(out, result.values, result.shape.count * sizeof(float));
	return (int)result.shape.count;
}
