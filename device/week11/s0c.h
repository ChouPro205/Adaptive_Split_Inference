/*
 * S0c v1 encoder (device side): one FP32 beat at s0 -> Rice body + FP16 scale, the C version of
 * encode() in contracts/s0c_v1_ref/s0c_v1_ref.py (S0C-V1, SHA-256 323ffaba...; the numpy code is
 * normative, steps 1-4 of its docstring). Portable C without Zephyr: the host test
 * (device/scripts/test_week11_s0c_host.py) compiles it with the firmware numerics flags
 * (-ffp-contract=off -fno-fast-math) and compares every byte with the reference and the golden set.
 *
 *   step 2  reduce 360 -> 46: bin i = [floor(360 i / 46), ceil(360 (i + 1) / 46)), float32 sum in index
 *           order divided by the float32 bin length (torch adaptive_avg_pool1d bins)
 *   step 3  week5_quantize() with one channel of 46 values (the registry v2 rule of the reference)
 *   step 4  body = q[0] (int8), k, then Rice(k) of the zigzag deltas q[i] - q[i-1], i = 1..45, packed
 *           most significant bit first, zero padded; k in 0..7 minimises the bit count, ties -> smaller k
 */
#ifndef WEEK11_S0C_H
#define WEEK11_S0C_H

#include <stddef.h>
#include <stdint.h>

#define S0C_N_IN 360u
#define S0C_N_OUT 46u
#define S0C_K_MAX 7u
/* Worst case: k = 7 is never worse than the chosen k, and |d| <= 254 gives z <= 508, so each of the
 * 45 words is at most (508 >> 7) + 1 + 7 = 11 bits: 2 + ceil(495 / 8) = 64 bytes. */
#define S0C_BODY_MAX 64u
#define S0C_VERSION "S0C-V1"

enum s0c_status {
	S0C_OK = 0,
	S0C_E_ARGUMENT = -1,   /* NULL buffer */
	S0C_E_DATA = -2,       /* NaN/Inf in the beat, or a scale outside the finite FP16 range */
	S0C_E_QUANT = -3,      /* week5_quantize() refused the reduced beat */
};

struct s0c_beat {
	float reduced[S0C_N_OUT];     /* step 2 output */
	int8_t q[S0C_N_OUT];          /* step 3 output */
	uint8_t scale_le[2];          /* FP16 scale, little-endian */
	uint8_t k;                    /* Rice parameter */
	uint8_t body[S0C_BODY_MAX];   /* step 4 output: body[0..body_len) */
	uint16_t body_len;
};

/* Step 2 alone (x: 360 FP32 values). */
int s0c_reduce46(const float *x, float *reduced);
/* Steps 2-4 of one beat. No heap; out is fully written on S0C_OK. */
int s0c_encode(const float *x, struct s0c_beat *out);

#endif
