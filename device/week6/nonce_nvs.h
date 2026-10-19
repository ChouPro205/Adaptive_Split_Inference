/*
 * Zephyr NVS backend of nonce_store on storage_partition (0xDC000, 4 x 4096 B) per
 * contracts/i2_nonce_provisioning_v1.md §2-§5, with the week 6 test hooks of decision D2
 * (simulated write failure / bad read-back / damaged records at the storage layer, so the
 * real records are never destroyed) and the DFU sentinel of §8 item 6.
 * Every function must be called from the application thread (Flash writes block).
 */
#ifndef WEEK6_NONCE_NVS_H
#define WEEK6_NONCE_NVS_H

#include <stdbool.h>
#include <stdint.h>

#include "nonce_store.h"

#define NONCE_ID_SENTINEL 0x49f0u

enum nonce_boot_hook {
    NONCE_HOOK_NONE,
    NONCE_HOOK_STATE_CRC,         /* flip one CRC byte of NONCE_STATE as read */
    NONCE_HOOK_STATE_MISSING,     /* NONCE_STATE reads as absent */
    NONCE_HOOK_PROVISION_CORRUPT, /* flip one byte of PROVISION as read */
    NONCE_HOOK_KEY_MISMATCH,      /* flip one key_check byte of NONCE_STATE, CRC recomputed */
    NONCE_HOOK_COUNT
};

struct nonce_nvs_info {
    bool mounted;
    int mount_err;
    enum nonce_status status;
    enum nonce_reason reason;
    uint64_t persisted;
    uint64_t next;
    uint64_t limit;
    uint32_t key_id;
    uint32_t sender_id;
    uint8_t kcv[NONCE_KCV_BYTES];
    uint32_t writes;              /* NONCE_STATE writes this boot (incl. failed) */
    uint32_t write_cycles_max;
    uint64_t write_cycles_total;
    bool boot_in_write;           /* previous soft reset landed inside an NVS write */
    bool boot_noinit_valid;
};

/* Mount and run the boot sequence of §5 (never writes Flash). */
void nonce_nvs_init(void);
void nonce_nvs_get_info(struct nonce_nvs_info *out);
/* Allocates one sequence under the mutex; fills the 12-byte nonce; -1 = I2 must stop. */
int nonce_nvs_allocate(uint64_t *sequence, uint8_t nonce[12]);
/* Bench key and label for protect(); NULL unless READY. */
const uint8_t *nonce_nvs_key(void);
enum nonce_prov_result nonce_nvs_provision(uint32_t key_id, uint32_t sender_id,
                                           const uint8_t key[NONCE_KEY_BYTES]);
/* §4 step 4: erase storage_partition, allowed only when NVS did not mount. */
int nonce_nvs_erase_unmountable(void);

/* Test hooks (D2). Each takes effect once. */
void nonce_nvs_fail_next_write(void);
void nonce_nvs_bad_next_readback(void);
/* Re-runs the boot sequence with a read hook active (RAM state rebuilt from Flash). */
void nonce_nvs_reboot_logic(enum nonce_boot_hook hook);
/* Forces the next allocate() to reserve a new block (skips the rest of the current one). */
void nonce_nvs_exhaust_block(void);

/* Every write that reached nvs_write() since boot (any record). */
uint32_t nonce_nvs_storage_writes(void);

int nonce_nvs_sentinel_write(uint8_t value[16]);
int nonce_nvs_sentinel_read(uint8_t value[16]);

#endif
