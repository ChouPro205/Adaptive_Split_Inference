/*
 * Optimized FP32 head, bit-identical to src/week4_head.c (TC7).
 *
 * week4_head.c is included unmodified (its hash is locked by the week 5 evidence): the
 * authenticated R3 weights are static arrays in head_parameters.h, so a second translation
 * unit would duplicate 438.6 KB of Flash. Both kernels therefore share the weights, the graph
 * and the two activation buffers. week4_run_head() keeps the project optimization level
 * (-Os, as measured in week 4); only the functions below are compiled with -O2.
 *
 * Same numerics: -ffp-contract=off (no FMA), and every output element accumulates its terms
 * in week 4's order (input channel, then kernel tap), starting from 0.0f, bias added last.
 * Changes are only in how the work is scheduled: padding checks are moved out of the inner
 * loop (only x = 0, 1, L-2, L-1 need them), pointers advance instead of recomputing indices,
 * four outputs of one channel are accumulated together so each weight is loaded once for four
 * multiplies (each of the four sums still sees its own terms in the original order), and the
 * linear layers compute four output neurons per pass over the input.
 */
#include "../src/week4_head.c"

#include "head_fast.h"

#pragma GCC push_options
#pragma GCC optimize("O2")

/* One output element exactly as week 4 computes it (zero padding by skipping taps). */
static inline float conv_point(const float *input, const float *w, unsigned in_channels,
			       unsigned length, int x)
{
	float sum = 0.0f;
	for (unsigned ic = 0; ic < in_channels; ++ic) {
		const float *row = input + ic * length;
		for (int k = 0; k < 5; ++k) {
			int source = x + k - 2;
			if (source >= 0 && source < (int)length) {
				sum += row[source] * w[k];
			}
		}
		w += 5;
	}
	return sum;
}

static void conv_fast(const struct head_op *op, const float *input, float *output)
{
	const unsigned length = op->length;
	const unsigned in_channels = op->in_channels;
	const unsigned last = length - 2U;  /* interior is x in [2, length - 2) */

	for (unsigned oc = 0; oc < op->out_channels; ++oc) {
		const float *w_oc = op->weight + oc * in_channels * 5U;
		const float bias = op->bias[oc];
		float *out = output + oc * length;

		out[0] = conv_point(input, w_oc, in_channels, length, 0) + bias;
		out[1] = conv_point(input, w_oc, in_channels, length, 1) + bias;

		unsigned x = 2U;
		for (; x + 4U <= last; x += 4U) {
			float s0 = 0.0f, s1 = 0.0f, s2 = 0.0f, s3 = 0.0f;
			const float *p = input + x - 2U;
			const float *w = w_oc;
			for (unsigned ic = 0; ic < in_channels; ++ic) {
				const float w0 = w[0], w1 = w[1], w2 = w[2], w3 = w[3], w4 = w[4];
				const float p0 = p[0], p1 = p[1], p2 = p[2], p3 = p[3];
				const float p4 = p[4], p5 = p[5], p6 = p[6], p7 = p[7];
				s0 += p0 * w0; s0 += p1 * w1; s0 += p2 * w2; s0 += p3 * w3; s0 += p4 * w4;
				s1 += p1 * w0; s1 += p2 * w1; s1 += p3 * w2; s1 += p4 * w3; s1 += p5 * w4;
				s2 += p2 * w0; s2 += p3 * w1; s2 += p4 * w2; s2 += p5 * w3; s2 += p6 * w4;
				s3 += p3 * w0; s3 += p4 * w1; s3 += p5 * w2; s3 += p6 * w3; s3 += p7 * w4;
				p += length;
				w += 5;
			}
			out[x] = s0 + bias;
			out[x + 1U] = s1 + bias;
			out[x + 2U] = s2 + bias;
			out[x + 3U] = s3 + bias;
		}
		for (; x < last; ++x) {
			float sum = 0.0f;
			const float *p = input + x - 2U;
			const float *w = w_oc;
			for (unsigned ic = 0; ic < in_channels; ++ic) {
				sum += p[0] * w[0];
				sum += p[1] * w[1];
				sum += p[2] * w[2];
				sum += p[3] * w[3];
				sum += p[4] * w[4];
				p += length;
				w += 5;
			}
			out[x] = sum + bias;
		}
		out[last] = conv_point(input, w_oc, in_channels, length, (int)last) + bias;
		out[last + 1U] = conv_point(input, w_oc, in_channels, length, (int)last + 1) + bias;
	}
}

static void relu_fast(float *values, unsigned count)
{
	for (float *end = values + count; values < end; ++values) {
		if (*values < 0.0f) {
			*values = 0.0f;
		}
	}
}

static void pool_fast(const struct head_op *op, const float *input, float *output)
{
	const unsigned half = op->length / 2U;  /* floor: features.19 pools L = 45 to 22 */
	for (unsigned channel = 0; channel < op->in_channels; ++channel) {
		const float *row = input + channel * op->length;
		for (unsigned x = 0; x < half; ++x) {
			const float left = row[2U * x];
			const float right = row[2U * x + 1U];
			*output++ = left > right ? left : right;
		}
	}
}

static void linear_fast(const struct head_op *op, const float *input, float *output)
{
	const unsigned in_channels = op->in_channels;
	unsigned oc = 0;
	for (; oc + 4U <= op->out_channels; oc += 4U) {
		const float *w0 = op->weight + oc * in_channels;
		const float *w1 = w0 + in_channels;
		const float *w2 = w1 + in_channels;
		const float *w3 = w2 + in_channels;
		float s0 = 0.0f, s1 = 0.0f, s2 = 0.0f, s3 = 0.0f;
		for (unsigned ic = 0; ic < in_channels; ++ic) {
			const float v = input[ic];
			s0 += v * w0[ic];
			s1 += v * w1[ic];
			s2 += v * w2[ic];
			s3 += v * w3[ic];
		}
		output[oc] = s0 + op->bias[oc];
		output[oc + 1U] = s1 + op->bias[oc + 1U];
		output[oc + 2U] = s2 + op->bias[oc + 2U];
		output[oc + 3U] = s3 + op->bias[oc + 3U];
	}
	for (; oc < op->out_channels; ++oc) {
		const float *w = op->weight + oc * in_channels;
		float sum = 0.0f;
		for (unsigned ic = 0; ic < in_channels; ++ic) {
			sum += input[ic] * w[ic];
		}
		output[oc] = sum + op->bias[oc];
	}
}

int head_fast_run(unsigned split, const float *input, struct week4_result *result)
{
	if (result == NULL) {
		return -1;
	}
	*result = (struct week4_result){0};
	if (input == NULL || week4_get_shape(split, &result->shape) != 0) {
		return -1;
	}
	const float *current = input;
	for (unsigned i = 0; i < split_op_counts[split]; ++i) {
		const struct head_op *op = &head_ops[i];
		float *next = current == activation_a ? activation_b : activation_a;
		switch (op->type) {
		case OP_CONV:
			conv_fast(op, current, next);
			current = next;
			break;
		case OP_RELU:
			relu_fast((float *)current, op->out_channels * op->length);
			break;
		case OP_POOL:
			pool_fast(op, current, next);
			current = next;
			break;
		case OP_LINEAR:
			linear_fast(op, current, next);
			current = next;
			break;
		case OP_IDENTITY:
			break;
		}
	}
	result->values = current;
	return 0;
}

#pragma GCC pop_options
