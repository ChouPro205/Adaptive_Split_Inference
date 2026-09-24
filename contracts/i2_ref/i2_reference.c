#include "i2_reference.h"

#include <limits.h>
#include <stdint.h>

#if CHAR_BIT != 8
#error "I2 requires 8-bit bytes"
#endif

static uint16_t load16(const uint8_t *p) {
    return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}

static uint32_t load32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static void store16(uint8_t *p, uint16_t value) {
    p[0] = (uint8_t)value;
    p[1] = (uint8_t)(value >> 8);
}

static void store32(uint8_t *p, uint32_t value) {
    p[0] = (uint8_t)value;
    p[1] = (uint8_t)(value >> 8);
    p[2] = (uint8_t)(value >> 16);
    p[3] = (uint8_t)(value >> 24);
}

static i2_status check_profile(const i2_profile *profile) {
    if (!profile || !profile->model_profile_id || !profile->split_id ||
        !profile->key_id || !profile->channels ||
        profile->channels > I2_MAX_CHANNELS || !profile->length ||
        !profile->max_payload_bytes ||
        profile->max_payload_bytes > I2_MAX_PAYLOAD_BYTES)
        return I2_INVALID_PROFILE;
    if ((uint64_t)profile->channels * profile->length > profile->max_payload_bytes)
        return I2_SIZE_LIMIT;
    return I2_OK;
}

i2_status i2_write_descriptor(const i2_profile *profile,
                              uint8_t output[I2_DESCRIPTOR_BYTES]) {
    if (!output) return I2_INVALID_ARGUMENT;
    i2_status status = check_profile(profile);
    if (status != I2_OK) return status;
    output[0] = 1;
    output[1] = 1;
    output[2] = 2;
    output[3] = 1;
    store32(output + 4, profile->model_profile_id);
    store16(output + 8, profile->split_id);
    store16(output + 10, 1);
    store16(output + 12, profile->channels);
    store16(output + 14, 0);
    store32(output + 16, profile->length);
    store32(output + 20, profile->key_id);
    store32(output + 24, (uint32_t)profile->channels * profile->length);
    return I2_OK;
}

static uint32_t rotl32(uint32_t value, unsigned bits) {
    return (value << bits) | (value >> (32u - bits));
}

static void quarter(uint32_t s[16], unsigned a, unsigned b, unsigned c, unsigned d) {
    s[a] += s[b]; s[d] = rotl32(s[d] ^ s[a], 16);
    s[c] += s[d]; s[b] = rotl32(s[b] ^ s[c], 12);
    s[a] += s[b]; s[d] = rotl32(s[d] ^ s[a], 8);
    s[c] += s[d]; s[b] = rotl32(s[b] ^ s[c], 7);
}

void i2_chacha20_block(const uint8_t key[32], uint32_t counter,
                       const uint8_t nonce[12], uint8_t output[64]) {
    uint32_t initial[16] = {0x61707865u, 0x3320646eu, 0x79622d32u, 0x6b206574u};
    uint32_t state[16];
    for (unsigned i = 0; i < 8; ++i) initial[4 + i] = load32(key + 4 * i);
    initial[12] = counter;
    for (unsigned i = 0; i < 3; ++i) initial[13 + i] = load32(nonce + 4 * i);
    for (unsigned i = 0; i < 16; ++i) state[i] = initial[i];
    for (unsigned round = 0; round < 10; ++round) {
        quarter(state, 0, 4, 8, 12);
        quarter(state, 1, 5, 9, 13);
        quarter(state, 2, 6, 10, 14);
        quarter(state, 3, 7, 11, 15);
        quarter(state, 0, 5, 10, 15);
        quarter(state, 1, 6, 11, 12);
        quarter(state, 2, 7, 8, 13);
        quarter(state, 3, 4, 9, 14);
    }
    for (unsigned i = 0; i < 16; ++i) store32(output + 4 * i, state[i] + initial[i]);
}

typedef struct {
    const uint8_t *key;
    const uint8_t *nonce;
    uint32_t counter;
    uint8_t block[64];
    unsigned position;
} byte_stream;

static uint8_t next_byte(byte_stream *s) {
    if (s->position == 64u) {
        i2_chacha20_block(s->key, s->counter++, s->nonce, s->block);
        s->position = 0;
    }
    return s->block[s->position++];
}

static uint32_t next_u32(byte_stream *s) {
    uint32_t result = 0;
    for (unsigned i = 0; i < 4; ++i) result |= (uint32_t)next_byte(s) << (8 * i);
    return result;
}

static uint8_t inverse_odd(uint8_t value) {
    for (unsigned candidate = 1; candidate < 256; candidate += 2) {
        if (((unsigned)value * candidate & 255u) == 1u) return (uint8_t)candidate;
    }
    return 0; /* Unreachable for odd value. */
}

static i2_status validate(const uint8_t *input, size_t input_len,
                          const uint8_t *metadata, size_t metadata_len,
                          const uint8_t *nonce, size_t nonce_len,
                          const uint8_t *key, size_t key_len,
                          const i2_profile *profile,
                          uint8_t *output, size_t output_capacity) {
    if (!input || !metadata || !nonce || !key || !profile || !output)
        return I2_INVALID_ARGUMENT;
    if (nonce_len != I2_NONCE_BYTES) return I2_INVALID_NONCE;
    if (key_len != I2_KEY_BYTES) return I2_KEY_UNAVAILABLE;
    i2_status profile_status = check_profile(profile);
    if (profile_status != I2_OK) return profile_status;
    if (metadata_len != I2_DESCRIPTOR_BYTES) return I2_INVALID_METADATA;
    if (metadata[0] != 1u) return I2_UNSUPPORTED_VERSION;
    if (metadata[1] != 1u) return I2_UNSUPPORTED_ALGORITHM;
    uint32_t model = load32(metadata + 4);
    uint16_t split = load16(metadata + 8);
    uint16_t n = load16(metadata + 10);
    uint16_t c = load16(metadata + 12);
    uint16_t reserved = load16(metadata + 14);
    uint32_t length = load32(metadata + 16);
    uint32_t key_id = load32(metadata + 20);
    uint32_t payload_length = load32(metadata + 24);
    if (metadata[2] != 2u || metadata[3] != 1u || !model || !split ||
        n != 1u || !c || reserved || !length || !key_id)
        return I2_INVALID_METADATA;
    uint64_t elements = (uint64_t)c * length;
    if (c > I2_MAX_CHANNELS || elements > I2_MAX_PAYLOAD_BYTES) return I2_SIZE_LIMIT;
    if (payload_length != elements || input_len != elements) return I2_LENGTH_MISMATCH;
    if (model != profile->model_profile_id || split != profile->split_id ||
        c != profile->channels || length != profile->length)
        return I2_PROFILE_MISMATCH;
    if (key_id != profile->key_id) return I2_KEY_SCOPE_MISMATCH;
    if (output_capacity < input_len) return I2_BUFFER_TOO_SMALL;
    uintptr_t src = (uintptr_t)input, dst = (uintptr_t)output;
    if ((dst >= src && dst - src < input_len) ||
        (src > dst && src - dst < input_len))
        return I2_INVALID_ARGUMENT;
    return I2_OK;
}

static i2_status transform(int inverse, const uint8_t *input, size_t input_len,
                           const uint8_t *metadata, size_t metadata_len,
                           const uint8_t *nonce, size_t nonce_len,
                           const uint8_t *key, size_t key_len,
                           const i2_profile *profile,
                           uint8_t *output, size_t output_capacity) {
    i2_status status = validate(input, input_len, metadata, metadata_len, nonce,
                                nonce_len, key, key_len, profile, output, output_capacity);
    if (status != I2_OK) return status;

    uint8_t a[I2_MAX_CHANNELS], b[I2_MAX_CHANNELS];
    uint16_t p[I2_MAX_CHANNELS];
    unsigned c = profile->channels;
    size_t length = profile->length;
    byte_stream stream = {key, nonce, 0, {0}, 64};
    for (unsigned i = 0; i < c; ++i) a[i] = (uint8_t)(next_byte(&stream) | 1u);
    for (unsigned i = 0; i < c; ++i) b[i] = next_byte(&stream);
    for (unsigned i = 0; i < c; ++i) p[i] = (uint16_t)i;
    for (unsigned i = c - 1; i > 0; --i) {
        uint64_t range = (uint64_t)i + 1u;
        uint64_t limit = (UINT64_C(1) << 32) - ((UINT64_C(1) << 32) % range);
        uint32_t sample;
        do { sample = next_u32(&stream); } while ((uint64_t)sample >= limit);
        unsigned j = (unsigned)((uint64_t)sample % range);
        uint16_t temp = p[i]; p[i] = p[j]; p[j] = temp;
    }
    for (unsigned out_channel = 0; out_channel < c; ++out_channel) {
        unsigned in_channel = p[out_channel];
        size_t source = (inverse ? out_channel : in_channel) * length;
        size_t target = (inverse ? in_channel : out_channel) * length;
        uint8_t inv = inverse ? inverse_odd(a[in_channel]) : 0;
        for (size_t pos = 0; pos < length; ++pos) {
            uint8_t value = input[source + pos];
            output[target + pos] = inverse
                ? (uint8_t)((unsigned)inv * (unsigned)((value - b[in_channel]) & 255u))
                : (uint8_t)((unsigned)a[in_channel] * value + b[in_channel]);
        }
    }
    return I2_OK;
}

i2_status i2_protect(const uint8_t *input, size_t input_len,
                     const uint8_t *metadata, size_t metadata_len,
                     const uint8_t *nonce, size_t nonce_len,
                     const uint8_t *key, size_t key_len,
                     const i2_profile *profile,
                     uint8_t *output, size_t output_capacity) {
    return transform(0, input, input_len, metadata, metadata_len, nonce,
                     nonce_len, key, key_len, profile, output, output_capacity);
}

i2_status i2_unprotect(const uint8_t *input, size_t input_len,
                       const uint8_t *metadata, size_t metadata_len,
                       const uint8_t *nonce, size_t nonce_len,
                       const uint8_t *key, size_t key_len,
                       const i2_profile *profile,
                       uint8_t *output, size_t output_capacity) {
    return transform(1, input, input_len, metadata, metadata_len, nonce,
                     nonce_len, key, key_len, profile, output, output_capacity);
}
