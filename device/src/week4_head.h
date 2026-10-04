#ifndef WEEK4_HEAD_H
#define WEEK4_HEAD_H

#include <stdint.h>

#define WEEK4_SPLIT_COUNT 11U
#define WEEK4_INPUT_COUNT 360U
#define WEEK4_BUFFER_COUNT 5760U

struct week4_shape {
	unsigned rank;
	unsigned dims[3];
	unsigned count;
};

struct week4_result {
	const float *values;
	struct week4_shape shape;
};

/* Single-threaded, no heap. A returned activation lives until the next call.
 * s=0 aliases the original input. Input must not alias the private workspace.
 * Each call restarts at input, never at the preceding split's activation.
 * Returns -1 for invalid arguments, clearing result when it is supplied.
 */
int week4_run_head(unsigned split, const float *input, struct week4_result *result);
int week4_get_shape(unsigned split, struct week4_shape *shape);

#endif
