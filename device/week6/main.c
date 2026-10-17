/*
 * Week 6 skeleton: BLE advertising and the I1 transport GATT service of
 * contracts/i1_ble_binding_v1.md §2 only. Fragment reassembly, I1 v2 encoding,
 * echo, P1 and nonce storage are later steps; RX writes are only counted here.
 */
#include <stdbool.h>
#include <stdint.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

BUILD_ASSERT(DT_NODE_HAS_COMPAT(DT_CHOSEN(zephyr_console), zephyr_cdc_acm_uart),
             "Week 6 requires USB CDC ACM as control/debug console");
BUILD_ASSERT(CONFIG_BT_MAX_CONN == 1, "Binding §1: one connection");

#define I1_UUID_SERVICE_VAL BT_UUID_128_ENCODE(0x74e40001, 0x0994, 0x465c, 0xbcd4, 0xb94671a54935)
#define I1_UUID_RX_VAL BT_UUID_128_ENCODE(0x74e40002, 0x0994, 0x465c, 0xbcd4, 0xb94671a54935)
#define I1_UUID_TX_VAL BT_UUID_128_ENCODE(0x74e40003, 0x0994, 0x465c, 0xbcd4, 0xb94671a54935)

static const struct bt_uuid_128 i1_service_uuid = BT_UUID_INIT_128(I1_UUID_SERVICE_VAL);
static const struct bt_uuid_128 i1_rx_uuid = BT_UUID_INIT_128(I1_UUID_RX_VAL);
static const struct bt_uuid_128 i1_tx_uuid = BT_UUID_INIT_128(I1_UUID_TX_VAL);

static atomic_t rx_writes;
static atomic_t rx_bytes;
static struct k_work adv_work;

static ssize_t rx_write(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf,
                        uint16_t len, uint16_t offset, uint8_t flags)
{
    ARG_UNUSED(conn);
    ARG_UNUSED(attr);
    ARG_UNUSED(buf);
    ARG_UNUSED(flags);
    /* Binding §2.1: no prepared/long writes. */
    if (offset != 0U) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
    }
    atomic_inc(&rx_writes);
    atomic_add(&rx_bytes, len);
    return len;
}

static void tx_ccc_changed(const struct bt_gatt_attr *attr, uint16_t value)
{
    ARG_UNUSED(attr);
    printk("TX CCC notify=%u\r\n", value == BT_GATT_CCC_NOTIFY ? 1U : 0U);
}

BT_GATT_SERVICE_DEFINE(i1_service,
    BT_GATT_PRIMARY_SERVICE(&i1_service_uuid),
    BT_GATT_CHARACTERISTIC(&i1_rx_uuid.uuid, BT_GATT_CHRC_WRITE | BT_GATT_CHRC_WRITE_WITHOUT_RESP,
                           BT_GATT_PERM_WRITE, NULL, rx_write, NULL),
    BT_GATT_CHARACTERISTIC(&i1_tx_uuid.uuid, BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_NONE,
                           NULL, NULL, NULL),
    BT_GATT_CCC(tx_ccc_changed, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
);

/* Binding §2.2: full 128-bit service UUID and the name fit in one 31-byte AD. */
static const struct bt_data adv_data[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
    BT_DATA_BYTES(BT_DATA_UUID128_ALL, I1_UUID_SERVICE_VAL),
    BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME, sizeof(CONFIG_BT_DEVICE_NAME) - 1),
};

static void adv_start(struct k_work *work)
{
    ARG_UNUSED(work);
    int err = bt_le_adv_start(BT_LE_ADV_CONN_FAST_1, adv_data, ARRAY_SIZE(adv_data), NULL, 0);
    printk("ADV start err=%d\r\n", err);
}

static void connected(struct bt_conn *conn, uint8_t err)
{
    printk("CONNECTED err=%u uatt_mtu=%u\r\n", err, err ? 0U : bt_gatt_get_uatt_mtu(conn));
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
    ARG_UNUSED(conn);
    printk("DISCONNECTED reason=0x%02x rx_writes=%ld rx_bytes=%ld\r\n", reason,
           (long)atomic_get(&rx_writes), (long)atomic_get(&rx_bytes));
}

/* Restart advertising only after the connection object is released. */
static void recycled(void)
{
    k_work_submit(&adv_work);
}

BT_CONN_CB_DEFINE(conn_callbacks) = {
    .connected = connected,
    .disconnected = disconnected,
    .recycled = recycled,
};

static void att_mtu_updated(struct bt_conn *conn, uint16_t tx, uint16_t rx)
{
    printk("ATT MTU tx=%u rx=%u uatt_mtu=%u frame_bytes_per_fragment=%u\r\n", tx, rx,
           bt_gatt_get_uatt_mtu(conn), bt_gatt_get_uatt_mtu(conn) - 11U);
}

static struct bt_gatt_cb gatt_callbacks = {
    .att_mtu_updated = att_mtu_updated,
};

#define STATS_MAX_THREADS 16

struct thread_stat {
    const char *name;
    size_t size;
    size_t unused;
};

static struct thread_stat stats[STATS_MAX_THREADS];
static unsigned stats_count;

/* Runs under the scheduler lock: only collect, print afterwards. */
static void collect_thread(const struct k_thread *thread, void *user_data)
{
    ARG_UNUSED(user_data);
    if (stats_count >= STATS_MAX_THREADS) {
        return;
    }
    size_t unused = 0;
    if (k_thread_stack_space_get(thread, &unused) != 0) {
        return;
    }
    const char *name = k_thread_name_get((k_tid_t)thread);
    stats[stats_count++] = (struct thread_stat){
        .name = (name != NULL && name[0] != '\0') ? name : "?",
        .size = thread->stack_info.size,
        .unused = unused,
    };
}

/* High-water marks need CONFIG_INIT_STACKS; one block every 5 s on the CDC console. */
static void print_stack_stats(void)
{
    stats_count = 0;
    k_thread_foreach(collect_thread, NULL);
    for (unsigned i = 0; i < stats_count; ++i) {
        printk("STACK %s used=%u size=%u\r\n", stats[i].name,
               (unsigned)(stats[i].size - stats[i].unused), (unsigned)stats[i].size);
    }
    printk("STATS uptime_ms=%lld rx_writes=%ld rx_bytes=%ld\r\n", k_uptime_get(),
           (long)atomic_get(&rx_writes), (long)atomic_get(&rx_bytes));
}

int main(void)
{
    k_work_init(&adv_work, adv_start);
    bt_gatt_cb_register(&gatt_callbacks);
    int err = bt_enable(NULL);
    if (err == 0) {
        k_work_submit(&adv_work);
    }
    for (;;) {
        printk("READY WEEK6 SKELETON name=%s bt_enable=%d l2cap_tx_mtu=%d acl_rx=%d\r\n",
               CONFIG_BT_DEVICE_NAME, err, CONFIG_BT_L2CAP_TX_MTU, CONFIG_BT_BUF_ACL_RX_SIZE);
        print_stack_stats();
        k_sleep(K_SECONDS(5));
    }
    return 0;
}
