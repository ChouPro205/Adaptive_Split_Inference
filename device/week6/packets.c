/* See packets.h. */
#include "packets.h"

#include "i1v2_codec.h"

static i2_profile profile_of(const struct pkt_tensor *t, uint32_t key_id)
{
    const i2_profile profile = {
        .model_profile_id = t->model_profile_id,
        .split_id = t->split_id,
        .channels = t->channels,
        .length = t->length,
        .key_id = key_id,
        .max_payload_bytes = PKT_MAX_PAYLOAD,
    };
    return profile;
}

i2_status pkt_descriptor(const struct pkt_tensor *t, uint32_t key_id,
                         uint8_t descriptor[I2_DESCRIPTOR_BYTES])
{
    const i2_profile profile = profile_of(t, key_id);
    return i2_write_descriptor(&profile, descriptor);
}

i2_status pkt_protect(const struct pkt_tensor *t, uint32_t key_id, const uint8_t *key,
                      const uint8_t nonce[I2_NONCE_BYTES],
                      const uint8_t descriptor[I2_DESCRIPTOR_BYTES], uint8_t *out,
                      size_t capacity)
{
    const i2_profile profile = profile_of(t, key_id);
    return i2_protect((const uint8_t *)t->q, (size_t)t->channels * t->length, descriptor,
                      I2_DESCRIPTOR_BYTES, nonce, I2_NONCE_BYTES, key, I2_KEY_BYTES, &profile,
                      out, capacity);
}

i2_status pkt_unprotect(const struct pkt_tensor *t, uint32_t key_id, const uint8_t *key,
                        const uint8_t nonce[I2_NONCE_BYTES],
                        const uint8_t descriptor[I2_DESCRIPTOR_BYTES],
                        const uint8_t *transformed, uint8_t *out, size_t capacity)
{
    const i2_profile profile = profile_of(t, key_id);
    return i2_unprotect(transformed, (size_t)t->channels * t->length, descriptor,
                        I2_DESCRIPTOR_BYTES, nonce, I2_NONCE_BYTES, key, I2_KEY_BYTES, &profile,
                        out, capacity);
}

size_t pkt_encode(uint8_t *out, size_t capacity, uint32_t request_id, const struct pkt_tensor *t,
                  const uint8_t *payload, const uint8_t *descriptor, const uint8_t *nonce)
{
    return i1v2_encode_request(out, capacity, request_id, t->model_profile_id, t->split_id,
                               t->channels, t->length, t->scale_bits, payload, descriptor, nonce);
}

uint32_t pkt_frame_length(uint16_t channels, uint32_t length, int transformed)
{
    return (transformed ? 108u : 68u) + 8u * channels + (uint32_t)channels * length;
}

uint32_t pkt_next_request_id(uint32_t *last)
{
    *last = *last == UINT32_MAX ? 1u : *last + 1u;
    return *last;
}
