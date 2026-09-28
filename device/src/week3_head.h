#ifndef WEEK3_HEAD_H
#define WEEK3_HEAD_H

#define WEEK3_INPUT_LENGTH 360
#define WEEK3_CHANNELS 16
#define WEEK3_OUTPUT_LENGTH 180
#define WEEK3_ACTIVATION_COUNT (WEEK3_CHANNELS * WEEK3_INPUT_LENGTH)
#define WEEK3_P2_COUNT (WEEK3_CHANNELS * WEEK3_OUTPUT_LENGTH)

/* M0 is already normalized by SV3. No preprocessing is performed here. */
void week3_conv1(const float *m0, float *m1);
void week3_relu(float *tensor, unsigned count);
void week3_conv2(const float *r1, float *m2);
void week3_pool(const float *r2, float *p2);

#endif
