/*
 * Optimized FP32 head (decision 17/10 with GV: new module, same numerics as week 4).
 * Same contract as week4_run_head(): single-threaded, no heap, the result lives until the
 * next call of either kernel (both share week 4's activation buffers), every call restarts
 * at the input. Output is bit-identical to week4_run_head() (TC7).
 */
#ifndef WEEK7_HEAD_FAST_H
#define WEEK7_HEAD_FAST_H

#include "week4_head.h"

int head_fast_run(unsigned split, const float *input, struct week4_result *result);

#endif
