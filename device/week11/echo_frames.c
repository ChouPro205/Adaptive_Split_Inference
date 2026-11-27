/* See echo_frames.h. */
#include "echo_frames.h"

#include <string.h>

#include "i1v2_codec.h"
#include "sha256.h"

static void put16(uint8_t *p, uint16_t v)
{
	p[0] = (uint8_t)v;
	p[1] = (uint8_t)(v >> 8);
}

static void put32(uint8_t *p, uint32_t v)
{
	p[0] = (uint8_t)v;
	p[1] = (uint8_t)(v >> 8);
	p[2] = (uint8_t)(v >> 16);
	p[3] = (uint8_t)(v >> 24);
}

/* Fixed header of a metadata-free, nonce-free I1 v2 envelope (I1 v2 §3). */
static void header(uint8_t *out, uint8_t message_type, uint32_t total, uint32_t request_id, uint16_t reserved_0)
{
	memset(out, 0, I1V2_FIXED_HEADER);
	memcpy(out, "I1PK", 4);
	out[4] = 2u;
	out[5] = message_type;
	put16(out + 8, I1V2_FIXED_HEADER);
	put16(out + 10, reserved_0);
	put32(out + 12, total);
	put32(out + 16, request_id);
	put32(out + 24, total - I1V2_FIXED_HEADER - I1V2_CRC_BYTES);
}

size_t echo_frame_build(uint8_t *out, size_t capacity, uint16_t length, uint32_t request_id, bool ack)
{
	if (out == NULL || length < ECHO_FRAME_MIN || length > ECHO_FRAME_MAX || capacity < length ||
	    request_id == 0u || request_id == UINT32_MAX) {
		return 0;
	}
	header(out, 0x01u, length, request_id, ack ? ECHO_MODE_ACK : ECHO_MODE_FULL);
	const uint32_t payload = (uint32_t)length - I1V2_FIXED_HEADER - I1V2_CRC_BYTES;
	for (uint32_t i = 0; i < payload; ++i) {
		out[I1V2_FIXED_HEADER + i] = (uint8_t)(i ^ (i >> 8) ^ request_id);
	}
	put32(out + length - I1V2_CRC_BYTES, i1v2_crc32(out, (size_t)length - I1V2_CRC_BYTES));
	return length;
}

void echo_ack_build(const uint8_t *sent, size_t sent_length, uint8_t out[ECHO_ACK_LENGTH])
{
	const uint32_t request_id = sent_length >= 20u ? ((uint32_t)sent[16] | ((uint32_t)sent[17] << 8) |
							  ((uint32_t)sent[18] << 16) | ((uint32_t)sent[19] << 24))
						       : 0u;
	header(out, 0x02u, ECHO_ACK_LENGTH, request_id, 0u);
	put32(out + I1V2_FIXED_HEADER, (uint32_t)sent_length);
	sha256(sent, sent_length, out + I1V2_FIXED_HEADER + 4u);
	put32(out + ECHO_ACK_LENGTH - I1V2_CRC_BYTES, i1v2_crc32(out, ECHO_ACK_LENGTH - I1V2_CRC_BYTES));
}

bool echo_ack_check(const uint8_t *ack, size_t ack_length, const uint8_t *sent, size_t sent_length)
{
	uint8_t want[ECHO_ACK_LENGTH];
	if (ack == NULL || sent == NULL || ack_length != ECHO_ACK_LENGTH) {
		return false;
	}
	echo_ack_build(sent, sent_length, want);
	return memcmp(ack, want, ECHO_ACK_LENGTH) == 0;
}
