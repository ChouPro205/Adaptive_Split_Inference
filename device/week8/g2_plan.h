/*
 * Week 8 session order and label rule, shared by the firmware and host_test/g2_shim.c (no Zephyr).
 * The laptop checker (week8_common.py) implements the same rules; test_week8_host.py compares them.
 */
#ifndef WEEK8_G2_PLAN_H
#define WEEK8_G2_PLAN_H

#include <stdbool.h>
#include <stdint.h>

#define G2_LOGITS 5u
#define G2_NO_LABEL 255u

/* W8-D1: pair k sends sample k mod count twice, P1 then P0 when k is even, P0 then P1 when odd. */
static inline unsigned g2_pair_sample(unsigned pair, unsigned count)
{
	return pair % count;
}

static inline bool g2_slot_is_p1(unsigned pair, unsigned slot)
{
	return ((pair + slot) % 2u) == 0u;
}

/* Index of the first largest logit (numpy argmax), G2_NO_LABEL if a logit is NaN. */
static inline uint8_t g2_label(const float logits[G2_LOGITS])
{
	unsigned best = 0;
	for (unsigned i = 0; i < G2_LOGITS; ++i) {
		if (logits[i] != logits[i]) {
			return G2_NO_LABEL;
		}
		if (logits[i] > logits[best]) {
			best = i;
		}
	}
	return (uint8_t)best;
}

#endif
