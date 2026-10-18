/*
 * I2/1 nonce high-water reservation and bench provisioning
 * (contracts/i2_nonce_provisioning_v1.md §3-§5). Portable C over a storage interface so
 * the host test can inject power loss and write failures and compare the record bytes
 * with contracts/i1v2_ref/nonce_reservation.py. The Zephyr NVS backend is nonce_nvs.c.
 * Not thread-safe: the caller holds one mutex around every call (contract §5).
 */
#ifndef WEEK6_NONCE_STORE_H
#define WEEK6_NONCE_STORE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define NONCE_ID_PROVISION 0x4901u
#define NONCE_ID_STATE 0x4902u
#define NONCE_PROVISION_BYTES 52u
#define NONCE_STATE_BYTES 36u
#define NONCE_KEY_BYTES 32u
#define NONCE_KCV_BYTES 8u
#define NONCE_RESERVE_BLOCK 1024u
#define NONCE_ERR_NOT_FOUND (-2) /* = -ENOENT, what nvs_read() returns for a missing ID */

/* read: bytes of the stored record (may exceed len), NONCE_ERR_NOT_FOUND, or < 0.
 * write: len on success, 0 if nothing was written, < 0 on error. */
struct nonce_storage {
    int (*read)(void *ctx, uint16_t id, uint8_t *buffer, size_t length);
    int (*write)(void *ctx, uint16_t id, const uint8_t *data, size_t length);
    void *ctx;
};

enum nonce_status { NONCE_READY, NONCE_UNPROVISIONED, NONCE_FAULT };

enum nonce_reason {
    NONCE_R_NONE,
    NONCE_R_MOUNT,
    NONCE_R_READ_ERROR,
    NONCE_R_PROVISION_CORRUPT,
    NONCE_R_STATE_MISSING,
    NONCE_R_STATE_CRC,
    NONCE_R_STATE_FORMAT,
    NONCE_R_STATE_KEY_MISMATCH,
    NONCE_R_NOT_IN_REGISTRY,
    NONCE_R_WRITE_FAILED,
    NONCE_R_WRITE_ZERO,
    NONCE_R_READBACK,
    NONCE_R_EXHAUSTED,
    NONCE_R_COUNT
};

extern const char *const nonce_reason_names[NONCE_R_COUNT];

struct nonce_alloc {
    const struct nonce_storage *storage;
    enum nonce_status status;
    enum nonce_reason reason;   /* why UNPROVISIONED/FAULT; latched until reboot */
    uint32_t key_id;
    uint32_t sender_id;
    uint8_t key[NONCE_KEY_BYTES];
    uint8_t kcv[NONCE_KCV_BYTES];
    uint64_t persisted;         /* reserved_through committed in storage */
    uint64_t next;
    uint64_t limit;             /* highest sequence usable in this boot */
    uint64_t block;
    uint32_t writes;            /* storage writes issued since boot */
};

/* Registry pair allowed for this profile (approved registry v2: 65537 / 131073). */
struct nonce_scope {
    uint32_t key_id;
    uint32_t sender_id;
};

void nonce_key_check(const uint8_t key[NONCE_KEY_BYTES], uint8_t out[NONCE_KCV_BYTES]);
void nonce_encode_state(uint8_t out[NONCE_STATE_BYTES], uint32_t key_id, uint32_t sender_id,
                        uint64_t reserved_through, const uint8_t kcv[NONCE_KCV_BYTES]);
void nonce_encode_provision(uint8_t out[NONCE_PROVISION_BYTES], uint32_t key_id,
                            uint32_t sender_id, const uint8_t key[NONCE_KEY_BYTES]);
/* 0 or the failing reason (STATE_MISSING/STATE_CRC/STATE_FORMAT). */
enum nonce_reason nonce_decode_state(const uint8_t *record, int length, uint32_t *key_id,
                                     uint32_t *sender_id, uint64_t *reserved_through,
                                     uint8_t kcv[NONCE_KCV_BYTES]);

/* Boot §5 steps 1-4. mounted=false gives FAULT/MOUNT. Never writes storage. */
void nonce_boot(struct nonce_alloc *a, const struct nonce_storage *storage, bool mounted,
                const struct nonce_scope *scope, uint64_t block);
/* §5 allocate(): 0 with *sequence, or -1 when I2 must stop (status FAULT, reason set). */
int nonce_allocate(struct nonce_alloc *a, uint64_t *sequence);
void nonce_make(const struct nonce_alloc *a, uint64_t sequence, uint8_t nonce[12]);

enum nonce_prov_result {
    NONCE_PROV_OK,
    NONCE_PROV_NOT_IN_REGISTRY,
    NONCE_PROV_STATE_IN_USE,    /* state with reserved_through > 0 exists: needs a new pair */
    NONCE_PROV_STATE_UNREADABLE,/* corrupt/foreign state or key record present */
    NONCE_PROV_WRITE_FAILED,
    NONCE_PROV_READBACK,
    NONCE_PROV_COUNT
};

extern const char *const nonce_prov_names[NONCE_PROV_COUNT];

/*
 * Bench provisioning §4 step 5: NONCE_STATE (reserved_through = 0) first, then PROVISION,
 * read back both. Refuses whenever a sequence might already have been used, so a key/pair
 * can never restart at sequence 1 (§4 step 7).
 */
enum nonce_prov_result nonce_provision(const struct nonce_storage *storage,
                                       const struct nonce_scope *scope, uint32_t key_id,
                                       uint32_t sender_id, const uint8_t key[NONCE_KEY_BYTES]);

#endif
