/* Host shim for test_week7_host.py: both kernels on the 20 authenticated R3 inputs. */
#include <stdint.h>
#include <string.h>

#include "head_fast.h"
#include "week4_inputs.h"

#if defined(_WIN32)
#define SHIM_EXPORT __declspec(dllexport)
#else
#define SHIM_EXPORT
#endif

/* kernel 0 = week 4 reference, 1 = fast. Copies the activation (FP32 bits) to out.
 * Returns the element count, or -1 on invalid arguments. */
SHIM_EXPORT int shim_run(int kernel, unsigned sample, unsigned split, uint32_t *out,
			 unsigned capacity)
{
	struct week4_result result;
	if (sample >= WEEK4_SAMPLE_COUNT) {
		return -1;
	}
	int status = kernel == 0 ? week4_run_head(split, week4_inputs[sample], &result)
				 : head_fast_run(split, week4_inputs[sample], &result);
	if (status != 0 || result.shape.count > capacity) {
		return -1;
	}
	memcpy(out, result.values, result.shape.count * sizeof(float));
	return (int)result.shape.count;
}

SHIM_EXPORT unsigned shim_sample_count(void)
{
	return WEEK4_SAMPLE_COUNT;
}
