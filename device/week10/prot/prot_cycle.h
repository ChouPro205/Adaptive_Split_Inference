/*
 * One week 10 E_prot cycle, radio off (W10-D1, W10-D2): week9/dev_cycle.h (hash-locked) plus the D1 PROT phase
 * of week8/g2_cycle.c (hash-locked), with (split, op) taken from the W10-D1 plan (week10_prot_plan.h):
 *   D4 CTRL  stub controller: the plan entry, padded to CONFIG_WEEK10_CTRL_MIN_US
 *   D0 HEAD  P1/P0: head to split s + INT8/FP16 quantization (+ exact FP32 scale expansion), as week 9
 *            CONV: head to s1 only (features.0 + ReLU), no quantization: the cheapest conv layer (E_conv,min)
 *   D1 PROT  P1 only: nonce from the block reserved at boot + descriptor + protect() (I2/1, bench key)
 * D2 TX and D3 WAIT are never driven. No Flash write inside a cycle: the boot reserved one nonce block and
 * the 500 P1 cycles of a session fit in it (nonce_writes must stay 0). No retry.
 */
#ifndef WEEK10_PROT_CYCLE_H
#define WEEK10_PROT_CYCLE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "i2_reference.h"

#define PROT_SPLITS 10u              /* s = 0..9 are sent (s10 is device-only: nothing to protect) */
#define PROT_HEAD_SPLITS 11u
#define PROT_CONV_SPLIT 1u           /* HEAD-only cycle: features.0 + ReLU */
#define PROT_MAX_VALUES 5760u        /* s1, s3 */
#define PROT_MAX_CHANNELS 64u        /* s7, s8 */

enum prot_op { PROT_OP_P0 = 0, PROT_OP_P1 = 1, PROT_OP_CONV = 2, PROT_OP_COUNT };

enum prot_error {
	PROT_OK,
	PROT_E_ARGUMENT,
	PROT_E_HEAD,
	PROT_E_QUANT,
	PROT_E_NONCE,
	PROT_E_PROTECT,
	PROT_E_COUNT
};

extern const char *const prot_error_names[PROT_E_COUNT];
extern const char *const prot_op_names[PROT_OP_COUNT];

/* Head output of one sample at one split (q, FP16 scales, FP32 scale bits), I2/I1 v2 ready. */
struct prot_tensor {
	unsigned split;
	unsigned sample;
	uint16_t channels;
	uint32_t length;
	const int8_t *q;
	const uint8_t *scale_le;     /* 2 * channels bytes, FP16 little-endian */
	const uint32_t *scale_bits;  /* channels words, exact FP32 expansion */
};

struct prot_result {
	enum prot_error error;
	unsigned cycle;
	unsigned sample;
	unsigned split;
	enum prot_op op;
	uint64_t sequence;           /* P1: nonce sequence used */
	uint32_t bytes_payload;      /* C * L int8 + 2 * C FP16 scale bytes (P1/P0) */
	uint32_t ctrl_cycles;
	uint32_t head_cycles;        /* D0 */
	uint32_t quant_cycles;       /* quantization part of head_cycles (P1/P0) */
	uint32_t prot_cycles;        /* D1 */
	uint32_t nonce_writes;       /* storage writes during the cycle (must be 0) */
	uint8_t digest[32];          /* P1: SHA-256 of the protected bytes (console only, after D1) */
};

/* The W8-D3 set (week8_inputs.h, rounds use samples 0..49) and the W10-D1 plan (week10_prot_plan.h). */
unsigned prot_sample_count(void);                /* WEEK10_PROT_PLAN_ROUNDS */
const char *prot_sample_id(unsigned sample);
const char *prot_set_sha256(void);
unsigned prot_plan_cycles(void);
unsigned prot_plan_split(unsigned cycle);
enum prot_op prot_plan_op(unsigned cycle);
unsigned prot_plan_sample(unsigned cycle);       /* cycle / 21 */
unsigned prot_plan_p1_cycles(unsigned first, unsigned count);
const char *prot_plan_sha256(void);
/* SHA-256 of the plan bytes (split, op) computed on the device, hex. */
void prot_plan_digest(char out[65]);

/* Fast FP32 kernel (W7-D8) + week 5 quantizer, exactly week9 dev_head(). */
int prot_head(unsigned split, unsigned sample, struct prot_tensor *out, uint32_t *head_cycles);
uint32_t prot_last_quant_cycles(void);
/* HEAD-only s1 (no quantization): the FP32 output (16 x 360) of sample n, valid until the next head. */
int prot_conv(unsigned sample, const float **values, unsigned *count);
/* descriptor + protect() of the tensor with the given key and nonce into out (C*L bytes); DWT cycles of
 * descriptor + protect in *cycles. Returns the I2 status. */
i2_status prot_protect(const struct prot_tensor *t, const uint8_t *key, const uint8_t nonce[12], uint8_t *out,
		       size_t capacity, uint32_t *cycles);
uint16_t prot_wire_split_id(unsigned split);

uint32_t prot_cycle_now(void);
void prot_cycle_init(void);
/* Cycle i of the W10-D1 plan (P1 needs the nonce store READY). */
void prot_cycle_run_plan(unsigned cycle, struct prot_result *r);
/* One cycle of (split, sample, op), the same body (console ONE). */
void prot_cycle_run(unsigned split, unsigned sample, enum prot_op op, struct prot_result *r);

#endif
