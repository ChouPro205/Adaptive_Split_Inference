/* See s0c.h. Numerics follow contracts/s0c_v1_ref/s0c_v1_ref.py step by step (float32 throughout). */
#include "s0c.h"

#include <math.h>
#include <string.h>

#include "quantization.h"

static unsigned bin_start(unsigned i)
{
	return (i * S0C_N_IN) / S0C_N_OUT;
}

static unsigned bin_end(unsigned i)
{
	return ((i + 1u) * S0C_N_IN + S0C_N_OUT - 1u) / S0C_N_OUT;
}

int s0c_reduce46(const float *x, float *reduced)
{
	if (x == NULL || reduced == NULL) {
		return S0C_E_ARGUMENT;
	}
	for (unsigned t = 0; t < S0C_N_IN; ++t) {
		if (!isfinite(x[t])) {
			return S0C_E_DATA;
		}
	}
	for (unsigned i = 0; i < S0C_N_OUT; ++i) {
		const unsigned a = bin_start(i), b = bin_end(i);
		float acc = 0.0f;
		for (unsigned t = a; t < b; ++t) {
			acc = acc + x[t];
		}
		reduced[i] = acc / (float)(b - a);
	}
	return S0C_OK;
}

static unsigned zigzag(int8_t previous, int8_t current)
{
	const int d = (int)current - (int)previous;
	return d >= 0 ? (unsigned)(2 * d) : (unsigned)(-2 * d - 1);
}

static unsigned rice_bits(const int8_t *q, unsigned k)
{
	unsigned bits = 0;
	for (unsigned i = 1; i < S0C_N_OUT; ++i) {
		bits += (zigzag(q[i - 1u], q[i]) >> k) + 1u + k;
	}
	return bits;
}

/* Appends one bit, most significant first; body was zeroed, so 0 bits only advance. */
static void put_bit(uint8_t *body, unsigned *position, unsigned bit)
{
	if (bit != 0u) {
		body[*position >> 3] |= (uint8_t)(0x80u >> (*position & 7u));
	}
	++*position;
}

static void rice_encode(const int8_t *q, struct s0c_beat *out)
{
	unsigned best_k = 0, best_bits = rice_bits(q, 0);
	for (unsigned k = 1; k <= S0C_K_MAX; ++k) {
		const unsigned bits = rice_bits(q, k);
		if (bits < best_bits) {   /* strict: ties keep the smaller k */
			best_bits = bits;
			best_k = k;
		}
	}
	memset(out->body, 0, sizeof(out->body));
	out->body[0] = (uint8_t)q[0];
	out->body[1] = (uint8_t)best_k;
	uint8_t *bits = out->body + 2;
	unsigned position = 0;
	for (unsigned i = 1; i < S0C_N_OUT; ++i) {
		const unsigned z = zigzag(q[i - 1u], q[i]);
		for (unsigned n = z >> best_k; n > 0u; --n) {
			put_bit(bits, &position, 0u);
		}
		put_bit(bits, &position, 1u);
		for (unsigned b = best_k; b > 0u; --b) {
			put_bit(bits, &position, (z >> (b - 1u)) & 1u);
		}
	}
	out->k = (uint8_t)best_k;
	out->body_len = (uint16_t)(2u + (position + 7u) / 8u);
}

int s0c_encode(const float *x, struct s0c_beat *out)
{
	if (out == NULL) {
		return S0C_E_ARGUMENT;
	}
	const int status = s0c_reduce46(x, out->reduced);
	if (status != S0C_OK) {
		return status;
	}
	const int quant = week5_quantize(out->reduced, S0C_N_OUT, 1u, 1u, S0C_N_OUT, out->q,
					 sizeof(out->q), out->scale_le, sizeof(out->scale_le));
	if (quant == WEEK5_DATA) {
		return S0C_E_DATA;
	}
	if (quant != WEEK5_OK) {
		return S0C_E_QUANT;
	}
	rice_encode(out->q, out);
	return S0C_OK;
}
