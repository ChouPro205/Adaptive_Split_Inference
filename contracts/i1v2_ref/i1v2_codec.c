/* I1 v2 C reference codec. See i1v2_codec.h and contracts/i1_device_edge_packet_v2.md. */
#include "i1v2_codec.h"

#include <string.h>

#define MSG_REQUEST 0x01u
#define MSG_RESPONSE 0x02u
#define MSG_ERROR 0x03u
#define FLAG_I2 0x0002u
#define DTYPE_INT8 0x02u
#define LAYOUT_NCL 0x01u
#define SCHEME_PER_CHANNEL 0x02u
#define REQUEST_PREFIX 32u
#define RESPONSE_META 8u

static uint16_t get16(const uint8_t *p)
{
	return (uint16_t)(p[0] | ((uint16_t)p[1] << 8));
}

static uint32_t get32(const uint8_t *p)
{
	return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
	       ((uint32_t)p[3] << 24);
}

static uint64_t get64(const uint8_t *p)
{
	return (uint64_t)get32(p) | ((uint64_t)get32(p + 4) << 32);
}

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

uint32_t i1v2_crc32(const uint8_t *data, size_t length)
{
	uint32_t crc = 0xffffffffu;
	for (size_t i = 0; i < length; i++) {
		crc ^= data[i];
		for (int bit = 0; bit < 8; bit++) {
			crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
		}
	}
	return crc ^ 0xffffffffu;
}

/* Positive normal FP16 expanded exactly: exponent 2^-14..2^15, low 13 mantissa bits 0. */
static int scale_bits_valid(uint32_t bits)
{
	uint32_t exponent = (bits >> 23) & 0xffu;
	return (bits >> 31) == 0u && exponent >= 113u && exponent <= 142u && (bits & 0x1fffu) == 0u;
}

static int float_bits_finite(uint32_t bits)
{
	return ((bits >> 23) & 0xffu) != 0xffu;
}

struct header {
	uint8_t version;
	uint8_t type;
	uint16_t flags;
	uint16_t header_length;
	uint16_t reserved_0;
	uint32_t total_length;
	uint32_t request_id;
	uint32_t metadata_length;
	uint32_t payload_length;
	uint16_t nonce_length;
	uint16_t reserved_1;
};

/* Stage A: magic, length identities with 64-bit arithmetic, limit, CRC. */
static int envelope(const uint8_t *p, size_t length, uint32_t max_packet, struct header *h)
{
	if (p == NULL || length < I1V2_FIXED_HEADER || memcmp(p, "I1PK", 4) != 0) {
		return I1V2_DROP;
	}
	h->version = p[4];
	h->type = p[5];
	h->flags = get16(p + 6);
	h->header_length = get16(p + 8);
	h->reserved_0 = get16(p + 10);
	h->total_length = get32(p + 12);
	h->request_id = get32(p + 16);
	h->metadata_length = get32(p + 20);
	h->payload_length = get32(p + 24);
	h->nonce_length = get16(p + 28);
	h->reserved_1 = get16(p + 30);
	if ((uint64_t)h->total_length != (uint64_t)length || h->total_length > max_packet) {
		return I1V2_DROP;
	}
	if ((uint64_t)h->header_length !=
	    (uint64_t)I1V2_FIXED_HEADER + h->metadata_length + h->nonce_length) {
		return I1V2_DROP;
	}
	if ((uint64_t)h->total_length !=
	    (uint64_t)h->header_length + h->payload_length + I1V2_CRC_BYTES) {
		return I1V2_DROP;
	}
	if (get32(p + length - I1V2_CRC_BYTES) != i1v2_crc32(p, length - I1V2_CRC_BYTES)) {
		return I1V2_DROP;
	}
	return 0;
}

int i1v2_parse_request(const uint8_t *p, size_t length, const struct i1v2_profile *profile,
		       uint32_t *request_id, struct i1v2_request *out)
{
	struct header h;
	const struct i1v2_split *split = NULL;

	if (profile == NULL || request_id == NULL || out == NULL ||
	    envelope(p, length, profile->max_packet, &h) != 0) {
		return I1V2_DROP;
	}
	*request_id = h.request_id;
	if (h.version != 2u) {
		return I1_UNSUPPORTED_VERSION;
	}
	if (h.type != MSG_REQUEST) {
		return I1_INVALID_MESSAGE_TYPE;
	}
	if (h.request_id == 0u) {
		return I1_INVALID_REQUEST_ID;
	}
	if (h.reserved_0 != 0u || h.reserved_1 != 0u) {
		return I1_INVALID_LENGTH;
	}
	if (h.flags != 0u && h.flags != FLAG_I2) {
		return I1_UNSUPPORTED_FLAGS;
	}
	const int transformed = h.flags == FLAG_I2;
	if (h.nonce_length != (transformed ? I1V2_NONCE_BYTES : 0u)) {
		return I1_INVALID_NONCE;
	}
	if (h.payload_length > profile->max_payload) {
		return I1_PAYLOAD_TOO_LARGE;
	}
	const uint8_t *m = p + I1V2_FIXED_HEADER;
	if (h.metadata_length < 16u) {
		return I1_INVALID_LENGTH;
	}
	if (get32(m) != profile->model_profile_id) {
		return I1_UNKNOWN_MODEL_PROFILE;
	}
	const uint16_t split_id = get16(m + 4);
	for (uint32_t i = 0; i < profile->split_count && i < I1V2_MAX_SPLITS; i++) {
		if (profile->splits[i].split_id == split_id) {
			split = &profile->splits[i];
			break;
		}
	}
	if (split == NULL) {
		return I1_UNSUPPORTED_SPLIT;
	}
	if (m[6] != DTYPE_INT8) {
		return I1_UNSUPPORTED_DTYPE;
	}
	if (m[7] != LAYOUT_NCL) {
		return I1_UNSUPPORTED_LAYOUT;
	}
	if (m[8] != 3u || m[11] != 0u) {
		return I1_INVALID_TENSOR_METADATA;
	}
	if (m[9] != SCHEME_PER_CHANNEL || (int8_t)m[10] != 1) {
		return I1_UNSUPPORTED_QUANTIZATION;
	}
	if (h.metadata_length < REQUEST_PREFIX) {
		return I1_INVALID_LENGTH;
	}
	const uint32_t channels = split->channels;
	const uint32_t element_count = channels * split->length; /* registry values, bounded */
	if (get32(m + 16) != 1u || get32(m + 20) != channels || get32(m + 24) != split->length ||
	    get32(m + 12) != element_count) {
		return I1_INVALID_TENSOR_METADATA;
	}
	if (h.payload_length != element_count) {
		return I1_INVALID_LENGTH;
	}
	if (get32(m + 28) != channels) {
		return I1_UNSUPPORTED_QUANTIZATION;
	}
	if ((uint64_t)h.metadata_length !=
	    (uint64_t)REQUEST_PREFIX + 8u * channels + (transformed ? I1V2_DESCRIPTOR_BYTES : 0u)) {
		return I1_INVALID_LENGTH;
	}
	for (uint32_t c = 0; c < channels; c++) {
		if (!scale_bits_valid(get32(m + REQUEST_PREFIX + 4u * c)) ||
		    get32(m + REQUEST_PREFIX + 4u * channels + 4u * c) != 0u) {
			return I1_UNSUPPORTED_QUANTIZATION;
		}
	}
	memset(out, 0, sizeof(*out));
	if (transformed) {
		const uint8_t *d = m + REQUEST_PREFIX + 8u * channels;
		if (d[0] != 1u || d[1] != 1u || d[2] != DTYPE_INT8 || d[3] != LAYOUT_NCL ||
		    get16(d + 10) != 1u || get16(d + 14) != 0u) {
			return I1_INVALID_I2_DESCRIPTOR;
		}
		if (get32(d + 4) != profile->model_profile_id || get16(d + 8) != split_id ||
		    get16(d + 12) != channels || get32(d + 16) != split->length ||
		    get32(d + 24) != element_count) {
			return I1_INVALID_I2_DESCRIPTOR;
		}
		if (get32(d + 20) != profile->key_id) {
			return I1_KEY_UNAVAILABLE;
		}
		const uint8_t *nonce = m + h.metadata_length;
		if (get32(nonce) != profile->sender_id || get64(nonce + 4) == 0u) {
			return I1_INVALID_NONCE;
		}
		out->descriptor_offset = (uint32_t)(d - p);
		out->nonce_offset = (uint32_t)(nonce - p);
	}
	out->request_id = h.request_id;
	out->flags = h.flags;
	out->split_id = split_id;
	out->channels = (uint16_t)channels;
	out->length = split->length;
	out->scales_offset = I1V2_FIXED_HEADER + REQUEST_PREFIX;
	out->payload_offset = h.header_length;
	out->payload_length = h.payload_length;
	return I1_OK;
}

int i1v2_parse_response(const uint8_t *p, size_t length, uint32_t expected_request_id,
			uint32_t max_packet, struct i1v2_response *out)
{
	struct header h;

	if (out == NULL || envelope(p, length, max_packet, &h) != 0) {
		return I1V2_DROP;
	}
	if (h.version != 2u || (h.type != MSG_RESPONSE && h.type != MSG_ERROR)) {
		return I1V2_DROP;
	}
	if (h.request_id == 0u || h.request_id != expected_request_id) {
		return I1V2_DROP;
	}
	if (h.reserved_0 != 0u || h.reserved_1 != 0u || h.flags != 0u || h.nonce_length != 0u ||
	    h.metadata_length != RESPONSE_META) {
		return I1V2_DROP;
	}
	const uint8_t *m = p + I1V2_FIXED_HEADER;
	const uint16_t status = get16(m);
	const uint32_t count = get32(m + 4);
	if (h.type == MSG_RESPONSE) {
		if (status != I1_OK || m[2] != 0x02u || m[3] != 0x02u || count != I1V2_RESULT_COUNT ||
		    h.payload_length != 4u * I1V2_RESULT_COUNT) {
			return I1V2_DROP;
		}
		for (uint32_t i = 0; i < I1V2_RESULT_COUNT; i++) {
			uint32_t bits = get32(p + h.header_length + 4u * i);
			if (!float_bits_finite(bits)) {
				return I1V2_DROP;
			}
			memcpy(&out->logits[i], &bits, sizeof(bits));
		}
	} else {
		if (status == I1_OK || status > I1_STATUS_LAST || m[2] != 0u || m[3] != 0u ||
		    count != 0u || h.payload_length != 0u) {
			return I1V2_DROP;
		}
		memset(out->logits, 0, sizeof(out->logits));
	}
	out->status = status;
	return 0;
}

static size_t finish(uint8_t *out, uint8_t type, uint16_t flags, uint32_t request_id,
		     uint32_t metadata_length, uint32_t nonce_length, uint32_t payload_length)
{
	const uint32_t header_length = I1V2_FIXED_HEADER + metadata_length + nonce_length;
	const uint32_t total = header_length + payload_length + I1V2_CRC_BYTES;

	memcpy(out, "I1PK", 4);
	out[4] = 2u;
	out[5] = type;
	put16(out + 6, flags);
	put16(out + 8, (uint16_t)header_length);
	put16(out + 10, 0u);
	put32(out + 12, total);
	put32(out + 16, request_id);
	put32(out + 20, metadata_length);
	put32(out + 24, payload_length);
	put16(out + 28, (uint16_t)nonce_length);
	put16(out + 30, 0u);
	put32(out + total - I1V2_CRC_BYTES, i1v2_crc32(out, total - I1V2_CRC_BYTES));
	return total;
}

size_t i1v2_encode_request(uint8_t *out, size_t capacity, uint32_t request_id,
			   uint32_t model_profile_id, uint16_t split_id, uint16_t channels,
			   uint32_t length, const uint32_t *scale_bits, const uint8_t *payload,
			   const uint8_t *descriptor, const uint8_t *nonce)
{
	const int transformed = descriptor != NULL;
	if (out == NULL || scale_bits == NULL || payload == NULL || (nonce != NULL) != transformed ||
	    request_id == 0u || channels == 0u || length == 0u ||
	    (uint64_t)channels * length > 0xffffu) {
		return 0;
	}
	const uint32_t payload_length = (uint32_t)channels * length;
	const uint32_t metadata_length =
		REQUEST_PREFIX + 8u * channels + (transformed ? I1V2_DESCRIPTOR_BYTES : 0u);
	const uint32_t nonce_length = transformed ? I1V2_NONCE_BYTES : 0u;
	const uint64_t total = (uint64_t)I1V2_FIXED_HEADER + metadata_length + nonce_length +
			       payload_length + I1V2_CRC_BYTES;
	if (total > capacity || I1V2_FIXED_HEADER + metadata_length + nonce_length > 0xffffu) {
		return 0;
	}
	uint8_t *m = out + I1V2_FIXED_HEADER;
	put32(m, model_profile_id);
	put16(m + 4, split_id);
	m[6] = DTYPE_INT8;
	m[7] = LAYOUT_NCL;
	m[8] = 3u;
	m[9] = SCHEME_PER_CHANNEL;
	m[10] = 1u;
	m[11] = 0u;
	put32(m + 12, payload_length);
	put32(m + 16, 1u);
	put32(m + 20, channels);
	put32(m + 24, length);
	put32(m + 28, channels);
	for (uint32_t c = 0; c < channels; c++) {
		put32(m + REQUEST_PREFIX + 4u * c, scale_bits[c]);
		put32(m + REQUEST_PREFIX + 4u * channels + 4u * c, 0u);
	}
	if (transformed) {
		memcpy(m + REQUEST_PREFIX + 8u * channels, descriptor, I1V2_DESCRIPTOR_BYTES);
		memcpy(m + metadata_length, nonce, I1V2_NONCE_BYTES);
	}
	memcpy(m + metadata_length + nonce_length, payload, payload_length);
	return finish(out, MSG_REQUEST, transformed ? FLAG_I2 : 0u, request_id, metadata_length,
		      nonce_length, payload_length);
}

size_t i1v2_encode_response(uint8_t *out, size_t capacity, uint32_t request_id,
			    const float logits[I1V2_RESULT_COUNT])
{
	const uint32_t payload_length = 4u * I1V2_RESULT_COUNT;
	if (out == NULL || logits == NULL || request_id == 0u ||
	    capacity < I1V2_FIXED_HEADER + RESPONSE_META + payload_length + I1V2_CRC_BYTES) {
		return 0;
	}
	uint8_t *m = out + I1V2_FIXED_HEADER;
	put16(m, I1_OK);
	m[2] = 0x02u;
	m[3] = 0x02u;
	put32(m + 4, I1V2_RESULT_COUNT);
	for (uint32_t i = 0; i < I1V2_RESULT_COUNT; i++) {
		uint32_t bits;
		memcpy(&bits, &logits[i], sizeof(bits));
		if (!float_bits_finite(bits)) {
			return 0;
		}
		put32(m + RESPONSE_META + 4u * i, bits);
	}
	return finish(out, MSG_RESPONSE, 0u, request_id, RESPONSE_META, 0u, payload_length);
}

size_t i1v2_encode_error(uint8_t *out, size_t capacity, uint32_t request_id, uint16_t status)
{
	if (out == NULL || status == I1_OK || status > I1_STATUS_LAST ||
	    capacity < I1V2_FIXED_HEADER + RESPONSE_META + I1V2_CRC_BYTES) {
		return 0;
	}
	uint8_t *m = out + I1V2_FIXED_HEADER;
	put16(m, status);
	m[2] = 0u;
	m[3] = 0u;
	put32(m + 4, 0u);
	return finish(out, MSG_ERROR, 0u, request_id, RESPONSE_META, 0u, 0u);
}
