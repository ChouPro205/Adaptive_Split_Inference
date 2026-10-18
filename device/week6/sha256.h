/* Minimal FIPS 180-4 SHA-256 for printing evidence hashes on the MCU. Host-tested against
 * Python hashlib (scripts/test_week6_host.py). Not used for any security decision. */
#ifndef WEEK6_SHA256_H
#define WEEK6_SHA256_H

#include <stddef.h>
#include <stdint.h>

struct sha256 {
    uint32_t h[8];
    uint64_t length;
    uint8_t block[64];
    uint32_t used;
};

void sha256_init(struct sha256 *s);
void sha256_update(struct sha256 *s, const uint8_t *data, size_t length);
void sha256_final(struct sha256 *s, uint8_t digest[32]);
void sha256(const uint8_t *data, size_t length, uint8_t digest[32]);
/* 64 lowercase hex characters plus NUL. */
void sha256_hex(const uint8_t digest[32], char out[65]);

#endif
