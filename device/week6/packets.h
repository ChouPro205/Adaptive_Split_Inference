/*
 * I1 v2 request building on the Device: optional I2/1 transform (contracts/i2_ref, compiled
 * unmodified) then framing (contracts/i1v2_ref/i1v2_codec.c, unmodified). Portable C.
 */
#ifndef WEEK6_PACKETS_H
#define WEEK6_PACKETS_H

#include <stddef.h>
#include <stdint.h>

#include "i2_reference.h"

#define PKT_MODEL_PROFILE_ID 1296651265u /* registry mitdb-week5-i2-registry-v1-r1 */
#define PKT_KEY_ID 65537u
#define PKT_SENDER_ID 131073u
#define PKT_MAX_PAYLOAD 5760u
#define PKT_MAX_CHANNELS 64u

/* One INT8 NCL tensor [1,C,L] with its FP16 scales already expanded to FP32 bits. */
struct pkt_tensor {
    uint32_t model_profile_id;
    uint16_t split_id;
    uint16_t channels;
    uint32_t length;
    const int8_t *q;
    const uint32_t *scale_bits;
};

/* I2/1 descriptor for the tensor and key label. Returns I2_OK or an i2_status. */
i2_status pkt_descriptor(const struct pkt_tensor *t, uint32_t key_id,
                         uint8_t descriptor[I2_DESCRIPTOR_BYTES]);
/* protect() of the q bytes into out (C*L bytes); descriptor from pkt_descriptor(). */
i2_status pkt_protect(const struct pkt_tensor *t, uint32_t key_id, const uint8_t *key,
                      const uint8_t nonce[I2_NONCE_BYTES],
                      const uint8_t descriptor[I2_DESCRIPTOR_BYTES], uint8_t *out,
                      size_t capacity);
i2_status pkt_unprotect(const struct pkt_tensor *t, uint32_t key_id, const uint8_t *key,
                        const uint8_t nonce[I2_NONCE_BYTES],
                        const uint8_t descriptor[I2_DESCRIPTOR_BYTES],
                        const uint8_t *transformed, uint8_t *out, size_t capacity);
/* Plain request when descriptor and nonce are NULL; payload = q or transformed bytes.
 * Returns the frame length, 0 on invalid arguments or capacity. */
size_t pkt_encode(uint8_t *out, size_t capacity, uint32_t request_id, const struct pkt_tensor *t,
                  const uint8_t *payload, const uint8_t *descriptor, const uint8_t *nonce);
/* Frame length without building it (I1 v2 §4 table). */
uint32_t pkt_frame_length(uint16_t channels, uint32_t length, int transformed);
/* request_id: never 0, wraps 0xffffffff -> 1 (I1 v2 §11). */
uint32_t pkt_next_request_id(uint32_t *last);

#endif
