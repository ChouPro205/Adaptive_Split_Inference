#ifndef WEEK5_QUANTIZATION_H
#define WEEK5_QUANTIZATION_H
#include <stddef.h>
#include <stdint.h>

enum week5_status { WEEK5_OK = 0, WEEK5_ARGUMENT = -1, WEEK5_SIZE = -2,
                   WEEK5_DATA = -3 };
/* IEEE binary32/binary16 RNE, independent of hardware FP16. NaNs are canonical.
 * Buffers must be aligned, valid for the advertised capacity and nonoverlapping.
 * No heap/state; all validation precedes output writes. Counts are elements,
 * except scale_capacity/scale_bytes which are serialized little-endian bytes.
 * NCL is also the NC adapter when L=1. Input is never modified. */
uint16_t week5_f32_to_f16(float value);
float week5_f16_to_f32(uint16_t bits);
int week5_quantize(const float *z, size_t z_count, size_t n, size_t c, size_t l,
                  int8_t *q, size_t q_capacity, uint8_t *scale_le, size_t scale_capacity);
int week5_dequantize(const int8_t *q, size_t q_count, size_t n, size_t c, size_t l,
                    const uint8_t *scale_le, size_t scale_bytes,
                    float *z, size_t z_capacity);
#endif
