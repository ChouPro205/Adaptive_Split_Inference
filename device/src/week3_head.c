#include "week3_head.h"
#include "head_parameters.h"

void week3_conv1(const float *m0, float *m1)
{
	for (unsigned oc = 0; oc < WEEK3_CHANNELS; ++oc) {
		for (unsigned x = 0; x < WEEK3_INPUT_LENGTH; ++x) {
			float sum = 0.0f;
			for (unsigned k = 0; k < 5; ++k) {
				int source = (int)x + (int)k - 2;
				if (source >= 0 && source < WEEK3_INPUT_LENGTH) {
					sum += m0[source] * sv3_conv1_weight[oc * 5 + k];
				}
			}
			m1[oc * WEEK3_INPUT_LENGTH + x] = sum + sv3_conv1_bias[oc];
		}
	}
}

void week3_relu(float *tensor, unsigned count)
{
	for (unsigned i = 0; i < count; ++i) {
		if (tensor[i] < 0.0f) {
			tensor[i] = 0.0f;
		}
	}
}

void week3_conv2(const float *r1, float *m2)
{
	for (unsigned oc = 0; oc < WEEK3_CHANNELS; ++oc) {
		for (unsigned x = 0; x < WEEK3_INPUT_LENGTH; ++x) {
			float sum = 0.0f;
			for (unsigned ic = 0; ic < WEEK3_CHANNELS; ++ic) {
				for (unsigned k = 0; k < 5; ++k) {
					int source = (int)x + (int)k - 2;
					if (source >= 0 && source < WEEK3_INPUT_LENGTH) {
						unsigned weight = (oc * WEEK3_CHANNELS + ic) * 5 + k;
						sum += r1[ic * WEEK3_INPUT_LENGTH + (unsigned)source] *
						       sv3_conv2_weight[weight];
					}
				}
			}
			m2[oc * WEEK3_INPUT_LENGTH + x] = sum + sv3_conv2_bias[oc];
		}
	}
}

void week3_pool(const float *r2, float *p2)
{
	for (unsigned channel = 0; channel < WEEK3_CHANNELS; ++channel) {
		for (unsigned x = 0; x < WEEK3_OUTPUT_LENGTH; ++x) {
			float left = r2[channel * WEEK3_INPUT_LENGTH + 2 * x];
			float right = r2[channel * WEEK3_INPUT_LENGTH + 2 * x + 1];
			p2[channel * WEEK3_OUTPUT_LENGTH + x] = left > right ? left : right;
		}
	}
}
