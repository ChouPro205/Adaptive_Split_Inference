/* See nonce_nvs.h. */
#include "nonce_nvs.h"

#include <errno.h>
#include <string.h>

#include <zephyr/drivers/flash.h>
#include <zephyr/kernel.h>
#include <zephyr/kvss/nvs.h>
#include <zephyr/linker/section_tags.h>
#include <zephyr/random/random.h>
#include <zephyr/storage/flash_map.h>
#include <zephyr/sys/atomic.h>

#include "ble_link.h"
#include "i1v2_codec.h"
#include "markers.h"
#include "packets.h"

BUILD_ASSERT(PARTITION_OFFSET(storage_partition) == 0xdc000, "nonce §2: storage at 0xDC000");
BUILD_ASSERT(PARTITION_SIZE(storage_partition) == 0x4000, "nonce §2: 4 x 4096 B");
BUILD_ASSERT(IS_ENABLED(CONFIG_NVS_DATA_CRC), "nonce §2: CONFIG_NVS_DATA_CRC=y");
BUILD_ASSERT(!IS_ENABLED(CONFIG_NVS_INIT_BAD_MEMORY_REGION), "nonce §2: never auto-format");

#define NOINIT_MAGIC 0x4e57364eu /* "N6WN" */
#define PHASE_IDLE 0u
#define PHASE_WRITING 0x57524954u

/* Survives a soft reset (not a power cut): was the reset inside an NVS write? */
struct noinit_marker {
    uint32_t magic;
    uint32_t phase;
    uint32_t check;
};
static __noinit struct noinit_marker noinit_marker;

static struct nvs_fs fs;
static K_MUTEX_DEFINE(nonce_lock);
static struct nonce_alloc alloc;
static const struct nonce_scope scope = {PKT_KEY_ID, PKT_SENDER_ID};
static bool mounted;
static int mount_err;
static bool fail_next_write;
static bool bad_next_readback;
static bool corrupt_reads;
static enum nonce_boot_hook boot_hook;
static uint32_t write_cycles_max;
static uint64_t write_cycles_total;
static bool boot_in_write;
static bool boot_noinit_valid;
static atomic_t storage_writes;

static void marker_set(uint32_t phase)
{
    noinit_marker.magic = NOINIT_MAGIC;
    noinit_marker.phase = phase;
    noinit_marker.check = NOINIT_MAGIC ^ phase;
}

static void put32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

static int storage_read(void *ctx, uint16_t id, uint8_t *buffer, size_t length)
{
    ARG_UNUSED(ctx);
    const ssize_t n = nvs_read(&fs, id, buffer, length);
    if (n == -ENOENT) {
        return NONCE_ERR_NOT_FOUND;
    }
    if (n < 0) {
        return (int)n;
    }
    const size_t got = MIN((size_t)n, length);
    if (corrupt_reads && id == NONCE_ID_STATE && got > 0) {
        corrupt_reads = false;
        buffer[got - 1] ^= 0x01u;
    }
    if (boot_hook == NONCE_HOOK_STATE_MISSING && id == NONCE_ID_STATE) {
        return NONCE_ERR_NOT_FOUND;
    }
    if (boot_hook == NONCE_HOOK_STATE_CRC && id == NONCE_ID_STATE && got == NONCE_STATE_BYTES) {
        buffer[32] ^= 0x01u;
    }
    if (boot_hook == NONCE_HOOK_KEY_MISMATCH && id == NONCE_ID_STATE && got == NONCE_STATE_BYTES) {
        buffer[24] ^= 0x01u;
        put32(buffer + 32, i1v2_crc32(buffer, 32));
    }
    if (boot_hook == NONCE_HOOK_PROVISION_CORRUPT && id == NONCE_ID_PROVISION && got > 20) {
        buffer[20] ^= 0x01u;
    }
    return (int)n;
}

static int storage_write(void *ctx, uint16_t id, const uint8_t *data, size_t length)
{
    ARG_UNUSED(ctx);
    if (fail_next_write) {
        fail_next_write = false;
        return -EIO;   /* D2: simulated Flash write failure, nothing is written */
    }
    /* D1: MARKER_PROTECTION (P0.15) high and the noinit phase show a write in progress. */
    atomic_inc(&storage_writes);
    marker_set(PHASE_WRITING);
    marker_on(MARKER_PROTECTION);
    const uint32_t start = link_cycles();
    const ssize_t n = nvs_write(&fs, id, data, length);
    const uint32_t cycles = link_cycles() - start;
    marker_off(MARKER_PROTECTION);
    marker_set(PHASE_IDLE);
    write_cycles_total += cycles;
    write_cycles_max = MAX(write_cycles_max, cycles);
    if (n > 0 && bad_next_readback) {
        bad_next_readback = false;
        corrupt_reads = true;   /* D2: the read-back after this write differs */
    }
    return (int)n;
}

static const struct nonce_storage storage = {storage_read, storage_write, NULL};

static int mount(void)
{
    struct flash_pages_info page;

    fs.flash_device = PARTITION_DEVICE(storage_partition);
    fs.offset = PARTITION_OFFSET(storage_partition);
    if (!device_is_ready(fs.flash_device)) {
        return -ENODEV;
    }
    int err = flash_get_page_info_by_offs(fs.flash_device, fs.offset, &page);
    if (err != 0) {
        return err;
    }
    fs.sector_size = (uint32_t)page.size;
    fs.sector_count = (uint16_t)(PARTITION_SIZE(storage_partition) / page.size);
    return nvs_mount(&fs);
}

void nonce_nvs_init(void)
{
    boot_noinit_valid = noinit_marker.magic == NOINIT_MAGIC &&
                        noinit_marker.check == (NOINIT_MAGIC ^ noinit_marker.phase);
    boot_in_write = boot_noinit_valid && noinit_marker.phase == PHASE_WRITING;
    marker_set(PHASE_IDLE);
    k_mutex_lock(&nonce_lock, K_FOREVER);
    mount_err = mount();
    mounted = mount_err == 0;
    nonce_boot(&alloc, &storage, mounted, &scope, NONCE_RESERVE_BLOCK);
    k_mutex_unlock(&nonce_lock);
}

void nonce_nvs_get_info(struct nonce_nvs_info *out)
{
    k_mutex_lock(&nonce_lock, K_FOREVER);
    *out = (struct nonce_nvs_info){
        .mounted = mounted,
        .mount_err = mount_err,
        .status = alloc.status,
        .reason = alloc.reason,
        .persisted = alloc.persisted,
        .next = alloc.next,
        .limit = alloc.limit,
        .key_id = alloc.key_id,
        .sender_id = alloc.sender_id,
        .writes = alloc.writes,
        .write_cycles_max = write_cycles_max,
        .write_cycles_total = write_cycles_total,
        .boot_in_write = boot_in_write,
        .boot_noinit_valid = boot_noinit_valid,
    };
    memcpy(out->kcv, alloc.kcv, NONCE_KCV_BYTES);
    k_mutex_unlock(&nonce_lock);
}

int nonce_nvs_allocate(uint64_t *sequence, uint8_t nonce[12])
{
    k_mutex_lock(&nonce_lock, K_FOREVER);
    const int err = nonce_allocate(&alloc, sequence);
    if (err == 0) {
        nonce_make(&alloc, *sequence, nonce);
    }
    k_mutex_unlock(&nonce_lock);
    return err;
}

const uint8_t *nonce_nvs_key(void)
{
    return alloc.status == NONCE_READY ? alloc.key : NULL;
}

enum nonce_prov_result nonce_nvs_provision(uint32_t key_id, uint32_t sender_id,
                                           const uint8_t key[NONCE_KEY_BYTES])
{
    k_mutex_lock(&nonce_lock, K_FOREVER);
    enum nonce_prov_result result = NONCE_PROV_WRITE_FAILED;
    if (mounted) {
        result = nonce_provision(&storage, &scope, key_id, sender_id, key);
        /* Same as a reboot: rebuild the RAM state from what is now in Flash. */
        nonce_boot(&alloc, &storage, mounted, &scope, NONCE_RESERVE_BLOCK);
    }
    k_mutex_unlock(&nonce_lock);
    return result;
}

int nonce_nvs_erase_unmountable(void)
{
    k_mutex_lock(&nonce_lock, K_FOREVER);
    int err = -EPERM;
    if (!mounted) {
        err = flash_erase(PARTITION_DEVICE(storage_partition), PARTITION_OFFSET(storage_partition),
                          PARTITION_SIZE(storage_partition));
        if (err == 0) {
            mount_err = mount();
            mounted = mount_err == 0;
            err = mount_err;
        }
        nonce_boot(&alloc, &storage, mounted, &scope, NONCE_RESERVE_BLOCK);
    }
    k_mutex_unlock(&nonce_lock);
    return err;
}

void nonce_nvs_fail_next_write(void)
{
    k_mutex_lock(&nonce_lock, K_FOREVER);
    fail_next_write = true;
    k_mutex_unlock(&nonce_lock);
}

void nonce_nvs_bad_next_readback(void)
{
    k_mutex_lock(&nonce_lock, K_FOREVER);
    bad_next_readback = true;
    k_mutex_unlock(&nonce_lock);
}

void nonce_nvs_exhaust_block(void)
{
    k_mutex_lock(&nonce_lock, K_FOREVER);
    if (alloc.status == NONCE_READY) {
        alloc.next = alloc.limit + 1u;   /* skipping sequences is always safe */
    }
    k_mutex_unlock(&nonce_lock);
}

void nonce_nvs_reboot_logic(enum nonce_boot_hook hook)
{
    k_mutex_lock(&nonce_lock, K_FOREVER);
    fail_next_write = false;
    bad_next_readback = false;
    corrupt_reads = false;
    boot_hook = hook;
    nonce_boot(&alloc, &storage, mounted, &scope, NONCE_RESERVE_BLOCK);
    boot_hook = NONCE_HOOK_NONE;
    k_mutex_unlock(&nonce_lock);
}

uint32_t nonce_nvs_storage_writes(void)
{
    return (uint32_t)atomic_get(&storage_writes);
}

int nonce_nvs_sentinel_write(uint8_t value[16])
{
    uint8_t record[20];
    sys_rand_get(value, 16);
    memcpy(record, value, 16);
    put32(record + 16, i1v2_crc32(record, 16));
    k_mutex_lock(&nonce_lock, K_FOREVER);
    atomic_inc(&storage_writes);
    const ssize_t n = mounted ? nvs_write(&fs, NONCE_ID_SENTINEL, record, sizeof(record)) : -ENODEV;
    k_mutex_unlock(&nonce_lock);
    return n == (ssize_t)sizeof(record) ? 0 : (n < 0 ? (int)n : -EIO);
}

int nonce_nvs_sentinel_read(uint8_t value[16])
{
    uint8_t record[20];
    k_mutex_lock(&nonce_lock, K_FOREVER);
    const ssize_t n = mounted ? nvs_read(&fs, NONCE_ID_SENTINEL, record, sizeof(record)) : -ENODEV;
    k_mutex_unlock(&nonce_lock);
    if (n != (ssize_t)sizeof(record)) {
        return n < 0 ? (int)n : -EIO;
    }
    const uint32_t crc = (uint32_t)record[16] | ((uint32_t)record[17] << 8) |
                         ((uint32_t)record[18] << 16) | ((uint32_t)record[19] << 24);
    if (crc != i1v2_crc32(record, 16)) {
        return -EBADMSG;
    }
    memcpy(value, record, 16);
    return 0;
}
