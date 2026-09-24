#ifndef I2_REFERENCE_H
#define I2_REFERENCE_H

#include <stddef.h>
#include <stdint.h>

#define I2_DESCRIPTOR_BYTES 28u
#define I2_NONCE_BYTES 12u
#define I2_KEY_BYTES 32u
#define I2_MAX_CHANNELS 256u
#define I2_MAX_PAYLOAD_BYTES 32768u

typedef struct {
    uint32_t model_profile_id;
    uint16_t split_id;
    uint16_t channels;
    uint32_t length;
    uint32_t key_id;
    uint32_t max_payload_bytes;
} i2_profile;

typedef enum {
    I2_OK = 0,
    I2_INVALID_ARGUMENT = 1,
    I2_INVALID_NONCE = 2,
    I2_KEY_UNAVAILABLE = 3,
    I2_INVALID_PROFILE = 4,
    I2_INVALID_METADATA = 5,
    I2_UNSUPPORTED_VERSION = 6,
    I2_UNSUPPORTED_ALGORITHM = 7,
    I2_SIZE_LIMIT = 8,
    I2_LENGTH_MISMATCH = 9,
    I2_PROFILE_MISMATCH = 10,
    I2_KEY_SCOPE_MISMATCH = 11,
    I2_BUFFER_TOO_SMALL = 12
} i2_status;

/* Reference block for the RFC 8439 test vector. */
void i2_chacha20_block(const uint8_t key[32], uint32_t counter,
                       const uint8_t nonce[12], uint8_t output[64]);

/* Serialize the I2/1 descriptor without using C struct layout. */
i2_status i2_write_descriptor(const i2_profile *profile,
                              uint8_t output[I2_DESCRIPTOR_BYTES]);

/* Input and output must not overlap. No allocation; output is untouched on error. */
i2_status i2_protect(const uint8_t *input, size_t input_len,
                     const uint8_t *metadata, size_t metadata_len,
                     const uint8_t *nonce, size_t nonce_len,
                     const uint8_t *key, size_t key_len,
                     const i2_profile *profile,
                     uint8_t *output, size_t output_capacity);

i2_status i2_unprotect(const uint8_t *input, size_t input_len,
                       const uint8_t *metadata, size_t metadata_len,
                       const uint8_t *nonce, size_t nonce_len,
                       const uint8_t *key, size_t key_len,
                       const i2_profile *profile,
                       uint8_t *output, size_t output_capacity);

#endif
