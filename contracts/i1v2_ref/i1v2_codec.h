/* I1 v2 C reference codec: framing and validation order only (no I2 transform,
 * no dynamic allocation). Host reference written independently of the Python
 * reference; not firmware or Edge production code. */
#ifndef I1V2_CODEC_H
#define I1V2_CODEC_H

#include <stddef.h>
#include <stdint.h>

#define I1V2_FIXED_HEADER 32u
#define I1V2_CRC_BYTES 4u
#define I1V2_DESCRIPTOR_BYTES 28u
#define I1V2_NONCE_BYTES 12u
#define I1V2_RESULT_COUNT 5u
#define I1V2_MAX_SPLITS 16u
#define I1V2_DROP (-1)

enum i1v2_status {
	I1_OK = 0x0000,
	I1_UNSUPPORTED_VERSION = 0x0001,
	I1_INVALID_MESSAGE_TYPE = 0x0002,
	I1_INVALID_LENGTH = 0x0003,
	I1_INVALID_TENSOR_METADATA = 0x0004,
	I1_CRC_MISMATCH = 0x0005,
	I1_UNSUPPORTED_SPLIT = 0x0006,
	I1_UNSUPPORTED_DTYPE = 0x0007,
	I1_EDGE_BUSY = 0x0008,
	I1_INFERENCE_FAILED = 0x0009,
	I1_TIMEOUT = 0x000a,
	I1_UNSUPPORTED_LAYOUT = 0x000b,
	I1_UNSUPPORTED_QUANTIZATION = 0x000c,
	I1_DUPLICATE_CONFLICT = 0x000d,
	I1_PAYLOAD_TOO_LARGE = 0x000e,
	I1_UNSUPPORTED_FLAGS = 0x000f,
	I1_INVALID_REQUEST_ID = 0x0010,
	I1_UNKNOWN_MODEL_PROFILE = 0x0011,
	I1_KEY_UNAVAILABLE = 0x0012,
	I1_INVALID_I2_DESCRIPTOR = 0x0013,
	I1_INVALID_NONCE = 0x0014,
	I1_STATUS_LAST = 0x0014
};

struct i1v2_split {
	uint16_t split_id;
	uint16_t channels;
	uint32_t length;
};

/* Active profile loaded from the approved registry revision. */
struct i1v2_profile {
	uint32_t model_profile_id;
	uint32_t key_id;
	uint32_t sender_id;
	uint32_t max_payload;
	uint32_t max_packet;
	uint32_t split_count;
	struct i1v2_split splits[I1V2_MAX_SPLITS];
};

/* Offsets into the caller's packet buffer; valid only when parse returns I1_OK. */
struct i1v2_request {
	uint32_t request_id;
	uint16_t flags;
	uint16_t split_id;
	uint16_t channels;
	uint32_t length;
	uint32_t scales_offset;
	uint32_t descriptor_offset; /* 0 when not transformed */
	uint32_t nonce_offset;      /* 0 when not transformed */
	uint32_t payload_offset;
	uint32_t payload_length;
};

struct i1v2_response {
	uint16_t status;
	float logits[I1V2_RESULT_COUNT];
};

uint32_t i1v2_crc32(const uint8_t *data, size_t length);

/* Returns I1V2_DROP (silent drop) or an I1 status; *request_id is set whenever
 * the result is not I1V2_DROP so the caller can build ERROR_RESPONSE. */
int i1v2_parse_request(const uint8_t *packet, size_t length, const struct i1v2_profile *profile,
		       uint32_t *request_id, struct i1v2_request *out);

/* Device side: 0 when accepted (status/logits filled), I1V2_DROP otherwise. */
int i1v2_parse_response(const uint8_t *packet, size_t length, uint32_t expected_request_id,
			uint32_t max_packet, struct i1v2_response *out);

/* Encoders return the frame length, or 0 if arguments/capacity are invalid.
 * scale_bits are FP32 bit patterns; descriptor and nonce are both NULL for a
 * plain request or both set for an I2/1 request (payload = transformed bytes). */
size_t i1v2_encode_request(uint8_t *out, size_t capacity, uint32_t request_id,
			   uint32_t model_profile_id, uint16_t split_id, uint16_t channels,
			   uint32_t length, const uint32_t *scale_bits, const uint8_t *payload,
			   const uint8_t *descriptor, const uint8_t *nonce);
size_t i1v2_encode_response(uint8_t *out, size_t capacity, uint32_t request_id,
			    const float logits[I1V2_RESULT_COUNT]);
size_t i1v2_encode_error(uint8_t *out, size_t capacity, uint32_t request_id, uint16_t status);

#endif
