#include "quantization.h"
#include <float.h>
#include <math.h>
#include <string.h>

#if FLT_RADIX != 2 || FLT_MANT_DIG != 24 || FLT_MAX_EXP != 128
#error "Week 5 requires IEEE binary32 float"
#endif
typedef char float_is_32_bits[(sizeof(float) == 4) ? 1 : -1];

static uint32_t shift_even(uint32_t x, unsigned shift)
{
    if (shift > 31U) { return 0; }
    uint32_t whole = x >> shift;
    uint32_t mask = (UINT32_C(1) << shift) - 1U;
    uint32_t half = UINT32_C(1) << (shift - 1U);
    uint32_t rest = x & mask;
    return whole + (rest > half || (rest == half && (whole & 1U)));
}

uint16_t week5_f32_to_f16(float value)
{
    uint32_t bits;
    memcpy(&bits, &value, sizeof(bits));
    uint16_t sign = (uint16_t)((bits >> 16) & 0x8000U);
    unsigned exp = (bits >> 23) & 0xffU;
    uint32_t frac = bits & 0x7fffffU;
    if (exp == 255U) { return (uint16_t)(sign | (frac ? 0x7e00U : 0x7c00U)); }
    int e = (int)exp - 127;
    if (e > 15) { return (uint16_t)(sign | 0x7c00U); }
    if (e < -25) { return sign; }
    if (e < -14) {
        return (uint16_t)(sign | shift_even(frac | 0x800000U, (unsigned)(-e - 1)));
    }
    /* Carry at a mantissa boundary naturally increments the stored exponent. */
    uint32_t rounded = shift_even(frac, 13U);
    return (uint16_t)(sign | (((unsigned)(e + 15) << 10) + rounded));
}

float week5_f16_to_f32(uint16_t half)
{
    uint32_t sign = (uint32_t)(half & 0x8000U) << 16;
    unsigned exp = (half >> 10) & 31U;
    uint32_t frac = half & 1023U;
    uint32_t bits;
    if (exp == 31U) { bits = sign | 0x7f800000U | (frac << 13); }
    else if (exp) { bits = sign | ((exp + 112U) << 23) | (frac << 13); }
    else if (!frac) { bits = sign; }
    else {
        int e = -14;
        while ((frac & 1024U) == 0) { frac <<= 1; --e; }
        bits = sign | ((uint32_t)(e + 127) << 23) | ((frac & 1023U) << 13);
    }
    float value;
    memcpy(&value, &bits, sizeof(value));
    return value;
}

static int shape(size_t n, size_t c, size_t l, size_t *channels, size_t *count)
{
    if (!n || !c || !l || n > SIZE_MAX / c) { return WEEK5_SIZE; }
    *channels = n * c;
    if (*channels > SIZE_MAX / l || *channels > SIZE_MAX / 2U) { return WEEK5_SIZE; }
    *count = *channels * l;
    return *count > SIZE_MAX / sizeof(float) ? WEEK5_SIZE : WEEK5_OK;
}

static int overlap(const void *a, size_t an, const void *b, size_t bn)
{
    uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    if (an > UINTPTR_MAX - x || bn > UINTPTR_MAX - y) { return 1; }
    return x < y + bn && y < x + an;
}

static int buffers(const float *z, size_t count, const int8_t *q,
                   const uint8_t *scale, size_t channels)
{
    if (!z || !q || !scale || (uintptr_t)z % sizeof(float) != 0) { return WEEK5_ARGUMENT; }
    if (overlap(z, count * sizeof(float), q, count) ||
        overlap(z, count * sizeof(float), scale, channels * 2U) ||
        overlap(q, count, scale, channels * 2U)) { return WEEK5_ARGUMENT; }
    return WEEK5_OK;
}

static int channel_scale(const float *z, size_t l, uint16_t *bits)
{
    float maximum = 0.0f;
    for (size_t i = 0; i < l; ++i) {
        if (!isfinite(z[i])) { return WEEK5_DATA; }
        float absolute = fabsf(z[i]);
        if (absolute > maximum) { maximum = absolute; }
    }
    float raw = maximum / 127.0f;
    if (raw > 65504.0f) { return WEEK5_DATA; }
    float stored = maximum == 0.0f ? 1.0f : (raw < 0x1p-14f ? 0x1p-14f : raw);
    *bits = week5_f32_to_f16(stored);
    return WEEK5_OK;
}

static int nearest_even(float value)
{
    /* value is already clipped to [-127,127]; int conversion is defined. */
    int whole = (int)value;
    float rest = value - (float)whole;
    if (rest > 0.5f || (rest == 0.5f && whole % 2 != 0)) { ++whole; }
    if (rest < -0.5f || (rest == -0.5f && whole % 2 != 0)) { --whole; }
    return whole;
}

int week5_quantize(const float *z, size_t z_count, size_t n, size_t c, size_t l,
                  int8_t *q, size_t q_capacity, uint8_t *scale_le, size_t scale_capacity)
{
    size_t channels, count;
    int status = shape(n, c, l, &channels, &count);
    if (status) { return status; }
    if (z_count != count || q_capacity < count || scale_capacity < 2U * channels) { return WEEK5_SIZE; }
    status = buffers(z, count, q, scale_le, channels);
    if (status) { return status; }
    for (size_t ch = 0; ch < channels; ++ch) {
        uint16_t bits;
        if (channel_scale(z + ch * l, l, &bits)) { return WEEK5_DATA; }
    }
    for (size_t ch = 0; ch < channels; ++ch) {
        uint16_t bits;
        (void)channel_scale(z + ch * l, l, &bits);
        scale_le[2U * ch] = (uint8_t)bits;
        scale_le[2U * ch + 1U] = (uint8_t)(bits >> 8);
        float effective = week5_f16_to_f32(bits);
        for (size_t i = 0; i < l; ++i) {
            float value = z[ch * l + i] / effective;
            if (value > 127.0f) { value = 127.0f; }
            if (value < -127.0f) { value = -127.0f; }
            q[ch * l + i] = (int8_t)nearest_even(value);
        }
    }
    return WEEK5_OK;
}

int week5_dequantize(const int8_t *q, size_t q_count, size_t n, size_t c, size_t l,
                    const uint8_t *scale_le, size_t scale_bytes, float *z, size_t z_capacity)
{
    size_t channels, count;
    int status = shape(n, c, l, &channels, &count);
    if (status) { return status; }
    if (q_count != count || z_capacity < count || scale_bytes != 2U * channels) { return WEEK5_SIZE; }
    status = buffers(z, count, q, scale_le, channels);
    if (status) { return status; }
    for (size_t ch = 0; ch < channels; ++ch) {
        uint16_t bits = (uint16_t)(scale_le[2U * ch] | ((uint16_t)scale_le[2U * ch + 1U] << 8));
        if (bits < 0x0400U || bits > 0x7bffU) { return WEEK5_DATA; }
    }
    for (size_t i = 0; i < count; ++i) { if (q[i] == -128) { return WEEK5_DATA; } }
    for (size_t ch = 0; ch < channels; ++ch) {
        uint16_t bits = (uint16_t)(scale_le[2U * ch] | ((uint16_t)scale_le[2U * ch + 1U] << 8));
        float effective = week5_f16_to_f32(bits);
        for (size_t i = 0; i < l; ++i) { z[ch * l + i] = (float)q[ch * l + i] * effective; }
    }
    return WEEK5_OK;
}
