#include "week4_head.h"
#include "head_parameters.h"

#include <stddef.h>

enum op_type { OP_CONV, OP_RELU, OP_POOL, OP_IDENTITY, OP_LINEAR };

struct head_op {
	enum op_type type;
	unsigned in_channels;
	unsigned out_channels;
	unsigned length;
	const float *weight;
	const float *bias;
};

/* Generated only from the authenticated R3 graph and split manifest. */
#include "week4_graph.h"

static float activation_a[WEEK4_BUFFER_COUNT];
static float activation_b[WEEK4_BUFFER_COUNT];

/* Generalization of Week 3's validated oc/x/ic/k accumulation order and
 * bias-after-sum FP32 kernels. Zero padding, OIK weights, NCL activation.
 */
static void conv(const struct head_op *op, const float *input, float *output)
{
	for (unsigned oc = 0; oc < op->out_channels; ++oc) {
		for (unsigned x = 0; x < op->length; ++x) {
			float sum = 0.0f;
			for (unsigned ic = 0; ic < op->in_channels; ++ic) {
				for (unsigned k = 0; k < 5; ++k) {
					int source = (int)x + (int)k - 2;
					if (source >= 0 && source < (int)op->length) {
						unsigned weight = (oc * op->in_channels + ic) * 5 + k;
						sum += input[ic * op->length + (unsigned)source] * op->weight[weight];
					}
				}
			}
			output[oc * op->length + x] = sum + op->bias[oc];
		}
	}
}

static void relu(float *values, unsigned count)
{
	for (unsigned i = 0; i < count; ++i) {
		if (values[i] < 0.0f) {
			values[i] = 0.0f;
		}
	}
}

static void pool(const struct head_op *op, const float *input, float *output)
{
	unsigned length = op->length / 2U;
	for (unsigned channel = 0; channel < op->in_channels; ++channel) {
		for (unsigned x = 0; x < length; ++x) {
			float left = input[channel * op->length + 2U * x];
			float right = input[channel * op->length + 2U * x + 1U];
			output[channel * length + x] = left > right ? left : right;
		}
	}
}

static void linear(const struct head_op *op, const float *input, float *output)
{
	for (unsigned oc = 0; oc < op->out_channels; ++oc) {
		float sum = 0.0f;
		for (unsigned ic = 0; ic < op->in_channels; ++ic) {
			sum += input[ic] * op->weight[oc * op->in_channels + ic];
		}
		output[oc] = sum + op->bias[oc];
	}
}

int week4_get_shape(unsigned split, struct week4_shape *shape)
{
	if (shape == NULL || split >= WEEK4_SPLIT_COUNT) {
		return -1;
	}
	*shape = split_shapes[split];
	return 0;
}

int week4_run_head(unsigned split, const float *input, struct week4_result *result)
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
			conv(op, current, next);
			current = next;
			break;
		case OP_RELU:
			relu((float *)current, op->out_channels * op->length);
			break;
		case OP_POOL:
			pool(op, current, next);
			current = next;
			break;
		case OP_LINEAR:
			linear(op, current, next);
			current = next;
			break;
		case OP_IDENTITY:
			/* Flatten preserves C order; eval Dropout has no scaling. */
			break;
		}
	}
	result->values = current;
	return 0;
}
