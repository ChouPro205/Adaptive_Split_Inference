/*
 * One week 9 E_dev cycle (W9-D2, W9-D5): week8/g2_cycle.h (hash-locked) cut to the phases that exist
 * without a link, with the split chosen per cycle (the W9-D4 plan now, several s over BLE in weeks
 * 10-11). The HEAD phase is unchanged from weeks 7-8 (W7-D2):
 *   D4 CTRL  stub controller: (s, sample) given by the caller, padded to CONFIG_WEEK9_CTRL_MIN_US
 *   D0 HEAD  head to split s + INT8/FP16 quantization (+ exact FP32 scale expansion)
 * D1 PROT, D2 TX and D3 WAIT are never driven: they stay LOW for the whole session (TC4).
 */
#ifndef WEEK9_DEV_CYCLE_H
#define WEEK9_DEV_CYCLE_H

#include <stdint.h>

#define DEV_SPLITS 11u          /* s = 0..10 (R3 mapping) */
#define DEV_MAX_VALUES 5760u    /* s1, s3: 16 x 360, 32 x 180 (results/week5/device/tensor_sizes.csv) */
#define DEV_MAX_CHANNELS 64u    /* s7, s8 */

enum dev_error {
	DEV_OK,
	DEV_E_ARGUMENT,
	DEV_E_HEAD,
	DEV_E_QUANT,
	DEV_E_COUNT
};

extern const char *const dev_error_names[DEV_E_COUNT];

/* Head output of one sample at one split (q, FP16 scales, FP32 scale bits), I1 v2 ready. */
struct dev_tensor {
	unsigned split;
	unsigned sample;
	uint16_t channels;
	uint32_t length;
	const int8_t *q;
	const uint8_t *scale_le;     /* 2 * channels bytes, FP16 little-endian */
	const uint32_t *scale_bits;  /* channels words, exact FP32 expansion */
};

struct dev_result {
	enum dev_error error;
	unsigned sample;
	unsigned split;
	uint32_t bytes_payload;      /* C * L int8 + 2 * C FP16 scale bytes */
	uint32_t ctrl_cycles;
	uint32_t head_cycles;        /* D0: head + quantization */
	uint32_t quant_cycles;       /* quantization part of head_cycles */
};

/* The W8-D3 set compiled into the image (week8_inputs.h) and the W9-D4 plan (week9_plan.h). */
unsigned dev_sample_count(void);                 /* samples measured: WEEK9_PLAN_ROUNDS */
const char *dev_sample_id(unsigned sample);
const char *dev_set_sha256(void);
unsigned dev_plan_cycles(void);
unsigned dev_plan_split(unsigned cycle);         /* split of cycle i of the plan */
unsigned dev_plan_sample(unsigned cycle);        /* round i / 11 uses sample i / 11 */
const char *dev_plan_sha256(void);               /* WEEK9_PLAN_SHA256 of the generator */
/* SHA-256 of the 550 plan bytes computed on the device, hex; equal to dev_plan_sha256(). */
void dev_plan_digest(char out[65]);

/* Fast FP32 kernel (W7-D8) + week 5 quantizer; the result aliases static buffers until the next
 * call. head_cycles (optional) receives the head-only part. */
int dev_head(unsigned split, unsigned sample, struct dev_tensor *out, uint32_t *head_cycles);
/* Cycles of the last dev_head() spent in quantization + scale expansion. */
uint32_t dev_last_quant_cycles(void);

/* DWT cycle counter (64 MHz), enabled by main(). */
uint32_t dev_cycle_now(void);

void dev_cycle_init(void);
/* CTRL then HEAD of (split, sample) with the D4/D0 markers. */
void dev_cycle_run(unsigned split, unsigned sample, struct dev_result *r);

#endif
