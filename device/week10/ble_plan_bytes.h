/*
 * Digest serialization of one W10-D4 plan entry, shared by ble_cycle.c and host_test/ble_shim.c (no
 * Zephyr): (split, rho, k, payload_bytes uint16 little-endian) = 5 bytes, the definition of
 * WEEK10_BLE_PLAN_SHA256 in week10_common.ble_plan_bytes(). The C struct has padding, so the bytes are
 * written field by field.
 */
#ifndef WEEK10_BLE_PLAN_BYTES_H
#define WEEK10_BLE_PLAN_BYTES_H

#include <stdint.h>

#include "week10_ble_plan.h"

#define BLE_PLAN_ENTRY_BYTES 5u

static inline void ble_plan_entry_bytes(const struct week10_ble_entry *e, uint8_t out[BLE_PLAN_ENTRY_BYTES])
{
	out[0] = e->split;
	out[1] = e->rho;
	out[2] = e->k;
	out[3] = (uint8_t)(e->payload_bytes & 0xffu);
	out[4] = (uint8_t)(e->payload_bytes >> 8);
}

#endif
