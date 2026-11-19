/*
 * One week 10 radio-on cycle at any split (W10-D4): week8/g2_cycle.h (hash-locked) with the split,
 * rho, link state and payload of every cycle taken from the W10-D4 plan (week10_ble_plan.h) and the
 * head of week9/dev_cycle.c (any s). Markers and phases are unchanged (W7-D2):
 *   D4 CTRL  stub controller: (s, rho, k, B) of the plan entry, padded to CONFIG_WEEK10_CTRL_MIN_US
 *   D0 HEAD  head to split s + INT8/FP16 quantization (+ exact FP32 scale expansion), as week 9
 *   D2 TX    I1 v2 encode + CRC32, every fragment until the last notify completes      (s <= 9)
 *   D3 WAIT  until a valid I1 v2 response for this request_id has been parsed, or the timeout (s <= 9)
 * s = 10 is the device-only cycle: CTRL + HEAD, then the label of the FP32 logits on the device; no
 * TX, no WAIT, the link stays connected. rho = 0 only in week 10 (D1 PROT is never driven: no nonce,
 * no NVS). The label is taken after the last phase, outside every phase. No retry.
 */
#ifndef WEEK10_BLE_CYCLE_H
#define WEEK10_BLE_CYCLE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "g2_plan.h"

#define BLE_SPLITS 11u               /* s = 0..10 (R3 mapping) */
#define BLE_DEVICE_ONLY_SPLIT 10u    /* full model on the dongle: no TX/WAIT */
#define BLE_MAX_VALUES 5760u         /* s1, s3 (results/week5/device/tensor_sizes.csv) */
#define BLE_MAX_CHANNELS 64u         /* s7, s8 */

enum ble_error {
	BLE_OK,
	BLE_E_ARGUMENT,      /* split > 10, rho != 0, k != 0 or payload_bytes != 0 (week 10 plan) */
	BLE_E_HEAD,
	BLE_E_QUANT,
	BLE_E_ENCODE,
	BLE_E_NOT_READY,
	BLE_E_TX,
	BLE_E_TIMEOUT,
	BLE_E_DISCONNECT,
	BLE_E_ERROR_RESPONSE,
	BLE_E_COUNT
};

extern const char *const ble_error_names[BLE_E_COUNT];

/* Head output of one sample at one split (q, FP16 scales, FP32 scale bits), I1 v2 ready. */
struct ble_tensor {
	unsigned split;
	unsigned sample;
	uint16_t channels;
	uint32_t length;
	const int8_t *q;
	const uint8_t *scale_le;     /* 2 * channels bytes, FP16 little-endian */
	const uint32_t *scale_bits;  /* channels words, exact FP32 expansion */
	const float *values;         /* FP32 head output (s10: the 5 logits), valid until the next head */
};

struct ble_result {
	enum ble_error error;
	unsigned cycle;              /* plan index, or 0 for ONE */
	unsigned sample;
	unsigned split;
	uint8_t rho;
	uint8_t k;
	uint16_t payload_req;        /* payload_bytes of the plan entry (0 = natural) */
	uint32_t bytes_payload;      /* C * L int8 + 2 * C FP16 scale bytes (Tensor column) */
	bool device_only;            /* s == 10 */
	uint32_t request_id;
	uint32_t frame_length;
	uint16_t att_mtu;
	uint16_t fragments;
	uint32_t enomem_retries;
	uint16_t response_status;
	float logits[G2_LOGITS];     /* received (s <= 9) or computed on the device (s10) */
	uint8_t label;               /* g2_label(logits) when error == BLE_OK, else G2_NO_LABEL */
	uint32_t ctrl_cycles;
	uint32_t head_cycles;        /* D0: head + quantization */
	uint32_t quant_cycles;       /* quantization part of head_cycles */
	uint32_t encode_cycles;      /* part of the TX phase */
	uint32_t tx_cycles;          /* D2 rising edge to the sender thread's result */
	uint32_t wait_cycles;
	uint32_t invalid_responses;
};

/* The W8-D3 set (week8_inputs.h, rounds use samples 0..49) and the W10-D4 plan (week10_ble_plan.h). */
unsigned ble_sample_count(void);                 /* samples measured: WEEK10_BLE_PLAN_ROUNDS */
const char *ble_sample_id(unsigned sample);
const char *ble_set_sha256(void);
unsigned ble_plan_cycles(void);
unsigned ble_plan_split(unsigned cycle);
unsigned ble_plan_sample(unsigned cycle);        /* round i / 11 uses sample i / 11 */
const char *ble_plan_sha256(void);               /* WEEK10_BLE_PLAN_SHA256 of the generator */
/* SHA-256 of the 5-byte serialization (split, rho, k, payload_bytes LE) of every entry, computed on
 * the device, hex; equal to ble_plan_sha256() for an intact plan. */
void ble_plan_digest(char out[65]);

/* Fast FP32 kernel (W7-D8) + week 5 quantizer, exactly week9 dev_head(); the result aliases static
 * buffers until the next call. head_cycles (optional) receives the head-only part. */
int ble_head(unsigned split, unsigned sample, struct ble_tensor *out, uint32_t *head_cycles);
uint32_t ble_last_quant_cycles(void);
/* Plain (rho0) I1 v2 request of the tensor into frame (FRAG_MAX_FRAME bytes); 0 on error. */
size_t ble_request(const struct ble_tensor *t, uint32_t request_id, uint8_t *frame);
uint16_t ble_wire_split_id(unsigned split);

/* DWT cycle counter (64 MHz), enabled by main() and by link_init(). */
uint32_t ble_cycle_now(void);

/* Random non-zero request_id start (I1 v2 §11), reassembler restricted to stream 0x01.
 * Call after link_init(). */
void ble_cycle_init(void);
/* Cycle i of the W10-D4 plan over the connected link (s10: on the device). */
void ble_cycle_run_plan(unsigned cycle, struct ble_result *r);
/* One rho0 cycle of (split, sample), the same body (console ONE). */
void ble_cycle_run(unsigned split, unsigned sample, struct ble_result *r);

#endif
