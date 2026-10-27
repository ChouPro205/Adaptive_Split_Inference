/*
 * One week 8 G2 cycle (W8-D6): week7/energy_cycle.h (hash-locked) with the 100 W8-D3 samples of
 * week8_inputs.h instead of the 20 R3 inputs, the sample chosen by the caller (paired session,
 * W8-D1) and the label read on the dongle. Markers and phases are unchanged (W7-D2):
 *   D4 CTRL  stub controller: fixed (s, rho) and the given sample, padded to CONFIG_WEEK7_CTRL_MIN_US
 *   D0 HEAD  head to split s + INT8/FP16 quantization (+ exact FP32 scale expansion)
 *   D1 PROT  rho = P1 only: nonce from the block reserved before the session, descriptor, protect()
 *   D2 TX    I1 v2 encode + CRC32, every fragment until the last notify completes
 *   D3 WAIT  until a valid I1 v2 response for this request_id has been parsed, or the timeout
 * The label (argmax of the received logits, g2_plan.h) is taken after D3, outside every phase.
 * No retry: a failed cycle is reported (energy-usb) and the checker rejects it.
 */
#ifndef WEEK8_G2_CYCLE_H
#define WEEK8_G2_CYCLE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "g2_plan.h"
#include "packets.h"

enum cycle_error {
	CYCLE_OK,
	CYCLE_E_HEAD,
	CYCLE_E_QUANT,
	CYCLE_E_NONCE,
	CYCLE_E_PROTECT,
	CYCLE_E_ENCODE,
	CYCLE_E_NOT_READY,
	CYCLE_E_TX,
	CYCLE_E_TIMEOUT,
	CYCLE_E_DISCONNECT,
	CYCLE_E_ERROR_RESPONSE,
	CYCLE_E_COUNT
};

extern const char *const cycle_error_names[CYCLE_E_COUNT];

/* Head output of one sample at one split, ready for I1 v2 (q, FP16 scales, FP32 scale bits). */
struct pipeline_tensor {
	unsigned split;
	unsigned sample;
	uint16_t channels;
	uint32_t length;
	const int8_t *q;
	const uint8_t *scale_le;     /* 2 * channels bytes, FP16 little-endian */
	const uint32_t *scale_bits;  /* channels words, exact FP32 expansion */
};

struct cycle_result {
	enum cycle_error error;
	bool p1;
	unsigned sample;
	unsigned split;
	uint32_t request_id;
	uint64_t sequence;
	uint32_t frame_length;
	uint16_t att_mtu;
	uint16_t fragments;
	uint32_t enomem_retries;
	uint16_t response_status;
	float logits[G2_LOGITS];
	uint8_t label;               /* g2_label(logits) when error == CYCLE_OK, else G2_NO_LABEL */
	uint32_t ctrl_cycles;
	uint32_t head_cycles;        /* head + quantization */
	uint32_t quant_cycles;       /* quantization part of head_cycles */
	uint32_t prot_cycles;
	uint32_t encode_cycles;      /* part of the TX phase */
	uint32_t tx_cycles;          /* D2 rising edge to the sender thread's result */
	uint32_t wait_cycles;
	uint32_t invalid_responses;
	uint32_t nonce_writes;       /* storage writes during the cycle (must be 0) */
};

/* The W8-D3 set compiled into the image (week8_inputs.h). */
unsigned g2_sample_count(void);
const char *g2_sample_id(unsigned sample);
uint8_t g2_reference_label(unsigned sample);   /* W8-D4: prediction_int8_fp16 at s=2 */
const char *g2_set_sha256(void);

/* Kernel selected by CONFIG_WEEK7_KERNEL_*; the result aliases the shared activation buffer. */
int pipeline_head(unsigned split, unsigned sample, struct pipeline_tensor *out);
/* I1 v2 request of the tensor into frame (FRAG_MAX_FRAME bytes); key/nonce NULL = plain. */
size_t pipeline_request(const struct pipeline_tensor *t, uint32_t request_id, const uint8_t *key,
			const uint8_t nonce[12], uint8_t *frame, uint32_t *prot_cycles);
uint16_t pipeline_wire_split_id(unsigned split);

/* DWT cycle counter (64 MHz), enabled by main() and by link_init(). */
uint32_t g2_cycle_now(void);

/* Random non-zero request_id start (I1 v2 §11), reassembler restricted to stream 0x01.
 * Call after link_init(). */
void g2_cycle_init(void);
/* Runs one cycle of the given sample over the connected link. */
void g2_cycle_run(unsigned sample, bool p1, struct cycle_result *r);

#endif
