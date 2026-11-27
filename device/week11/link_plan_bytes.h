/*
 * Digest serialization of the W11-D3 link plan, shared by link_cycle.c and host_test/link_shim.c (no Zephyr):
 * per state (index, phy, interval uint16 LE, latency uint16 LE, timeout uint16 LE, tx_octets, tx_power_dbm)
 * = 10 bytes, then per entry (op, state, a uint16 LE, b uint16 LE) = 6 bytes; the definition of
 * WEEK11_LINK_PLAN_SHA256 in week11_common.plan_bytes(). The C structs have padding, so the bytes are written
 * field by field.
 */
#ifndef WEEK11_LINK_PLAN_BYTES_H
#define WEEK11_LINK_PLAN_BYTES_H

#include <stdint.h>

#include "sha256.h"
#include "week11_link_plan.h"

#define LINK_STATE_BYTES 10u
#define LINK_ENTRY_BYTES 6u

static inline void link_state_bytes(const struct week11_link_state *s, uint8_t out[LINK_STATE_BYTES])
{
	out[0] = s->index;
	out[1] = s->phy;
	out[2] = (uint8_t)(s->interval_1250us & 0xffu);
	out[3] = (uint8_t)(s->interval_1250us >> 8);
	out[4] = (uint8_t)(s->latency & 0xffu);
	out[5] = (uint8_t)(s->latency >> 8);
	out[6] = (uint8_t)(s->timeout_10ms & 0xffu);
	out[7] = (uint8_t)(s->timeout_10ms >> 8);
	out[8] = s->tx_octets;
	out[9] = (uint8_t)s->tx_power_dbm;
}

static inline void link_entry_bytes(const struct week11_link_entry *e, uint8_t out[LINK_ENTRY_BYTES])
{
	out[0] = e->op;
	out[1] = e->state;
	out[2] = (uint8_t)(e->a & 0xffu);
	out[3] = (uint8_t)(e->a >> 8);
	out[4] = (uint8_t)(e->b & 0xffu);
	out[5] = (uint8_t)(e->b >> 8);
}

/* SHA-256 (hex) of the compiled state table and plan. */
static inline void link_plan_digest_hex(char out[65])
{
	struct sha256 ctx;
	uint8_t digest[32];
	sha256_init(&ctx);
	for (unsigned i = 0; i < WEEK11_LINK_STATES; ++i) {
		uint8_t bytes[LINK_STATE_BYTES];
		link_state_bytes(&week11_link_states[i], bytes);
		sha256_update(&ctx, bytes, sizeof(bytes));
	}
	for (unsigned i = 0; i < WEEK11_LINK_PLAN_ENTRIES; ++i) {
		uint8_t bytes[LINK_ENTRY_BYTES];
		link_entry_bytes(&week11_link_plan[i], bytes);
		sha256_update(&ctx, bytes, sizeof(bytes));
	}
	sha256_final(&ctx, digest);
	sha256_hex(digest, out);
}

#endif
