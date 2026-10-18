/* See ble_link.h. Rules: contracts/i1_ble_binding_v1.md §2-§5, §10. */
#include "ble_link.h"

#include <errno.h>
#include <string.h>

#include <cmsis_core.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/printk.h>

#include "markers.h"

BUILD_ASSERT(CONFIG_BT_MAX_CONN == 1, "Binding §1: one connection");
BUILD_ASSERT(LINK_TX_CREDITS <= CONFIG_BT_CONN_TX_MAX, "Binding §4.3: credits <= BT_CONN_TX_MAX");
BUILD_ASSERT(LINK_TX_CREDITS < CONFIG_BT_ATT_TX_COUNT, "Keep an ATT buffer for write responses");
BUILD_ASSERT(CONFIG_BT_L2CAP_TX_MTU <= 247, "tx_fragment holds ATT_MTU - 3 bytes for MTU <= 247");

#define I1_UUID_SERVICE_VAL BT_UUID_128_ENCODE(0x74e40001, 0x0994, 0x465c, 0xbcd4, 0xb94671a54935)
#define I1_UUID_RX_VAL BT_UUID_128_ENCODE(0x74e40002, 0x0994, 0x465c, 0xbcd4, 0xb94671a54935)
#define I1_UUID_TX_VAL BT_UUID_128_ENCODE(0x74e40003, 0x0994, 0x465c, 0xbcd4, 0xb94671a54935)
#define TX_THREAD_STACK 2048
#define TX_THREAD_PRIORITY 5
#define ENOMEM_SLEEP_MS 2

static const struct bt_uuid_128 i1_service_uuid = BT_UUID_INIT_128(I1_UUID_SERVICE_VAL);
static const struct bt_uuid_128 i1_rx_uuid = BT_UUID_INIT_128(I1_UUID_RX_VAL);
static const struct bt_uuid_128 i1_tx_uuid = BT_UUID_INIT_128(I1_UUID_TX_VAL);

K_SEM_DEFINE(link_wake, 0, 1);
static K_SEM_DEFINE(tx_credits, LINK_TX_CREDITS, LINK_TX_CREDITS);
static K_SEM_DEFINE(tx_job, 0, 1);
static K_SEM_DEFINE(tx_last, 0, 1);

static struct k_spinlock lock;          /* conn, reassembler, link_info, TX bookkeeping */
static struct bt_conn *current_conn;
static struct link_info info;
static uint8_t rx_buffer[FRAG_MAX_FRAME];
static struct reasm rx;

static atomic_t tx_busy;
static atomic_t tx_abort;
static atomic_t tx_generation;
static uint16_t tx_last_transfer_id;    /* per connection (§4.2) */
static const uint8_t *tx_frame;
static uint16_t tx_length;
static uint8_t tx_stream;
static uint8_t tx_fragment[FRAG_HEADER + 244];
static struct link_tx_result tx_result;
static bool tx_result_ready;
static volatile uint32_t tx_last_done_ms;
static volatile uint32_t tx_last_done_cycles;
static struct k_work adv_work;

uint32_t link_cycles(void)
{
    __asm__ volatile("" ::: "memory");
    const uint32_t cycles = DWT->CYCCNT;
    __asm__ volatile("" ::: "memory");
    return cycles;
}

static void wake(void)
{
    k_sem_give(&link_wake);
}

static ssize_t rx_write(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf,
                        uint16_t len, uint16_t offset, uint8_t flags)
{
    ARG_UNUSED(conn);
    ARG_UNUSED(attr);
    ARG_UNUSED(flags);
    /* Binding §2.1: no prepared/long writes. */
    if (offset != 0U) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
    }
    /* §5: header checks and one memcpy of at most ATT_MTU - 11 bytes; nothing else here. */
    k_spinlock_key_t key = k_spin_lock(&lock);
    info.rx_writes++;
    info.rx_bytes += len;
    const bool frame = reasm_feed(&rx, buf, len, k_uptime_get_32());
    k_spin_unlock(&lock, key);
    if (frame) {
        wake();
    }
    return len;
}

static void tx_ccc_changed(const struct bt_gatt_attr *attr, uint16_t value)
{
    ARG_UNUSED(attr);
    printk("EVT TX_CCC notify=%u\r\n", value == BT_GATT_CCC_NOTIFY ? 1U : 0U);
    wake();
}

BT_GATT_SERVICE_DEFINE(i1_service,
    BT_GATT_PRIMARY_SERVICE(&i1_service_uuid),
    BT_GATT_CHARACTERISTIC(&i1_rx_uuid.uuid, BT_GATT_CHRC_WRITE | BT_GATT_CHRC_WRITE_WITHOUT_RESP,
                           BT_GATT_PERM_WRITE, NULL, rx_write, NULL),
    BT_GATT_CHARACTERISTIC(&i1_tx_uuid.uuid, BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_NONE,
                           NULL, NULL, NULL),
    BT_GATT_CCC(tx_ccc_changed, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
);

#define TX_VALUE_ATTR (&i1_service.attrs[4])

/* Binding §2.2: full 128-bit service UUID and the name fit in one 31-byte AD. */
static const struct bt_data adv_data[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
    BT_DATA_BYTES(BT_DATA_UUID128_ALL, I1_UUID_SERVICE_VAL),
    BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME, sizeof(CONFIG_BT_DEVICE_NAME) - 1),
};

static void adv_start(struct k_work *work)
{
    ARG_UNUSED(work);
    const int err = bt_le_adv_start(BT_LE_ADV_CONN_FAST_1, adv_data, ARRAY_SIZE(adv_data), NULL, 0);
    printk("EVT ADV_START err=%d\r\n", err);
}

static void reset_credits(void)
{
    k_sem_reset(&tx_credits);
    for (int i = 0; i < LINK_TX_CREDITS; ++i) {
        k_sem_give(&tx_credits);
    }
}

static void connected(struct bt_conn *conn, uint8_t err)
{
    if (err != 0U) {
        printk("EVT CONNECT_FAILED err=%u\r\n", err);
        return;
    }
    struct bt_conn_info ci;
    k_spinlock_key_t key = k_spin_lock(&lock);
    current_conn = bt_conn_ref(conn);
    tx_last_transfer_id = 0;  /* §4.2: restart per connection */
    info.connected = true;
    info.connections++;
    if (bt_conn_get_info(conn, &ci) == 0) {
        info.interval_1250us = (uint16_t)(ci.le.interval_us / 1250U);
        info.latency = ci.le.latency;
        info.timeout_10ms = ci.le.timeout;
    }
    k_spin_unlock(&lock, key);
    atomic_set(&tx_abort, 0);
    reset_credits();
    k_sem_reset(&tx_last);
    printk("EVT CONNECTED uatt_mtu=%u interval_1250us=%u latency=%u timeout_10ms=%u\r\n",
           bt_gatt_get_uatt_mtu(conn), info.interval_1250us, info.latency, info.timeout_10ms);
    wake();
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
    k_spinlock_key_t key = k_spin_lock(&lock);
    if (current_conn == conn) {
        bt_conn_unref(current_conn);
        current_conn = NULL;
    }
    reasm_disconnect(&rx);
    info.connected = false;
    info.subscribed = false;
    info.disconnections++;
    info.last_disconnect_reason = reason;
    k_spin_unlock(&lock, key);
    /* Pending notifications never complete now: release a sender blocked on them. */
    atomic_set(&tx_abort, 1);
    reset_credits();
    k_sem_give(&tx_last);
    printk("EVT DISCONNECTED reason=0x%02x\r\n", reason);
    wake();
}

/* Restart advertising only after the connection object is released. */
static void recycled(void)
{
    k_work_submit(&adv_work);
}

static void le_param_updated(struct bt_conn *conn, uint16_t interval, uint16_t latency,
                             uint16_t timeout)
{
    ARG_UNUSED(conn);
    k_spinlock_key_t key = k_spin_lock(&lock);
    info.interval_1250us = interval;
    info.latency = latency;
    info.timeout_10ms = timeout;
    k_spin_unlock(&lock, key);
    printk("EVT CONN_PARAM interval_1250us=%u latency=%u timeout_10ms=%u\r\n", interval, latency,
           timeout);
}

static void le_phy_updated(struct bt_conn *conn, struct bt_conn_le_phy_info *param)
{
    ARG_UNUSED(conn);
    info.tx_phy = param->tx_phy;
    info.rx_phy = param->rx_phy;
    printk("EVT PHY tx=%u rx=%u\r\n", param->tx_phy, param->rx_phy);
}

#if defined(CONFIG_BT_USER_DATA_LEN_UPDATE)
/* Absent in the mtu23 variant: 27 B ACL buffers disable Data Length Extension. */
static void le_data_len_updated(struct bt_conn *conn, struct bt_conn_le_data_len_info *param)
{
    ARG_UNUSED(conn);
    info.tx_data_len = param->tx_max_len;
    info.rx_data_len = param->rx_max_len;
    printk("EVT DATA_LEN tx=%u rx=%u\r\n", param->tx_max_len, param->rx_max_len);
}
#endif

BT_CONN_CB_DEFINE(conn_callbacks) = {
    .connected = connected,
    .disconnected = disconnected,
    .recycled = recycled,
    .le_param_updated = le_param_updated,
    .le_phy_updated = le_phy_updated,
#if defined(CONFIG_BT_USER_DATA_LEN_UPDATE)
    .le_data_len_updated = le_data_len_updated,
#endif
};

static void att_mtu_updated(struct bt_conn *conn, uint16_t tx, uint16_t rx_mtu)
{
    printk("EVT ATT_MTU tx=%u rx=%u uatt_mtu=%u frame_bytes_per_fragment=%u\r\n", tx, rx_mtu,
           bt_gatt_get_uatt_mtu(conn), frag_data_bytes(bt_gatt_get_uatt_mtu(conn)));
    wake();
}

static struct bt_gatt_cb gatt_callbacks = {
    .att_mtu_updated = att_mtu_updated,
};

static struct bt_conn *conn_get(void)
{
    k_spinlock_key_t key = k_spin_lock(&lock);
    struct bt_conn *conn = current_conn != NULL ? bt_conn_ref(current_conn) : NULL;
    k_spin_unlock(&lock, key);
    return conn;
}

bool link_ready(void)
{
    struct bt_conn *conn = conn_get();
    bool ready = false;
    if (conn != NULL) {
        /* §2.3: connected, notifications enabled, ATT MTU known. */
        ready = bt_gatt_is_subscribed(conn, TX_VALUE_ATTR, BT_GATT_CCC_NOTIFY) &&
                bt_gatt_get_uatt_mtu(conn) != 0U;
        bt_conn_unref(conn);
    }
    info.subscribed = ready;
    return ready;
}

uint16_t link_mtu(void)
{
    struct bt_conn *conn = conn_get();
    uint16_t mtu = 0;
    if (conn != NULL) {
        mtu = bt_gatt_get_uatt_mtu(conn);
        bt_conn_unref(conn);
    }
    return mtu;
}

void link_get_info(struct link_info *out)
{
    const uint16_t mtu = link_mtu();
    (void)link_ready();
    k_spinlock_key_t key = k_spin_lock(&lock);
    *out = info;
    k_spin_unlock(&lock, key);
    out->att_mtu = mtu;
}

uint32_t link_disconnections(void)
{
    k_spinlock_key_t key = k_spin_lock(&lock);
    const uint32_t n = info.disconnections;
    k_spin_unlock(&lock, key);
    return n;
}

int link_disconnect(void)
{
    struct bt_conn *conn = conn_get();
    if (conn == NULL) {
        return -ENOTCONN;
    }
    const int err = bt_conn_disconnect(conn, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
    bt_conn_unref(conn);
    return err;
}

int link_request_conn_params(uint16_t min_1250us, uint16_t max_1250us, uint16_t latency,
                             uint16_t timeout_10ms)
{
    struct bt_conn *conn = conn_get();
    if (conn == NULL) {
        return -ENOTCONN;
    }
    const struct bt_le_conn_param param = BT_LE_CONN_PARAM_INIT(min_1250us, max_1250us, latency,
                                                                timeout_10ms);
    const int err = bt_conn_le_param_update(conn, &param);
    bt_conn_unref(conn);
    return err;
}

/* Completion of one notification (system workqueue): return the credit (§4.3). */
static void notify_done(struct bt_conn *conn, void *user_data)
{
    ARG_UNUSED(conn);
    const uintptr_t tag = (uintptr_t)user_data;
    k_sem_give(&tx_credits);
    if ((tag & 1U) != 0U && (tag >> 1) == (uintptr_t)atomic_get(&tx_generation)) {
        tx_last_done_cycles = link_cycles();
        tx_last_done_ms = k_uptime_get_32();
        k_sem_give(&tx_last);
    }
}

static enum link_tx_status transfer(struct bt_conn *conn, struct link_tx_result *r)
{
    const uint16_t mtu = bt_gatt_get_uatt_mtu(conn);
    const uint16_t chunk = frag_data_bytes(mtu);   /* §4.1: MTU read at the start of each transfer */
    if (chunk == 0U || !bt_gatt_is_subscribed(conn, TX_VALUE_ATTR, BT_GATT_CCC_NOTIFY)) {
        return LINK_TX_NOTCONN;
    }
    k_spinlock_key_t key = k_spin_lock(&lock);
    const uint16_t transfer_id = frag_next_transfer_id(&tx_last_transfer_id);
    k_spin_unlock(&lock, key);
    const uintptr_t generation = (uintptr_t)atomic_inc(&tx_generation) + 1U;
    k_sem_reset(&tx_last);
    r->transfer_id = transfer_id;
    r->att_mtu = mtu;
    r->start_ms = k_uptime_get_32();
    const uint32_t start_cycles = link_cycles();

    for (uint32_t offset = 0; offset < tx_length; offset += chunk) {
        const uint16_t n = (uint16_t)MIN((uint32_t)chunk, tx_length - offset);
        const bool last = offset + n == tx_length;
        frag_write_header(tx_fragment, tx_stream, transfer_id, (uint16_t)offset, tx_length);
        memcpy(tx_fragment + FRAG_HEADER, tx_frame + offset, n);
        struct bt_gatt_notify_params params = {
            .attr = TX_VALUE_ATTR,
            .data = tx_fragment,
            .len = (uint16_t)(FRAG_HEADER + n),
            .func = notify_done,
            .user_data = (void *)((generation << 1) | (last ? 1U : 0U)),
        };
        /* One credit per notification; the credit wait and -ENOMEM retries share the deadline. */
        const int64_t deadline = k_uptime_get() + LINK_TX_CREDIT_TIMEOUT_MS;
        for (;;) {
            const int64_t remaining = deadline - k_uptime_get();
            if (remaining <= 0 || k_sem_take(&tx_credits, K_MSEC(remaining)) != 0) {
                return LINK_TX_STALL;
            }
            if (atomic_get(&tx_abort) != 0) {
                return LINK_TX_NOTCONN;
            }
            const int err = bt_gatt_notify_cb(conn, &params);
            if (err == 0) {
                break;
            }
            k_sem_give(&tx_credits);
            if (err == -ENOMEM || err == -ENOBUFS) {
                r->enomem_retries++;
                k_sleep(K_MSEC(ENOMEM_SLEEP_MS));
                continue;
            }
            return LINK_TX_NOTCONN;   /* -ENOTCONN and anything else: abort the transfer */
        }
        r->fragments++;
        info.notifications++;
    }
    /* §4.3: the last fragment's completion marks the frame as handed to the stack. */
    if (k_sem_take(&tx_last, K_MSEC(LINK_TX_CREDIT_TIMEOUT_MS)) != 0) {
        return LINK_TX_STALL;
    }
    if (atomic_get(&tx_abort) != 0) {
        return LINK_TX_NOTCONN;
    }
    r->done_ms = tx_last_done_ms;
    r->cycles = tx_last_done_cycles - start_cycles;
    return LINK_TX_DONE;
}

static void tx_thread(void *a, void *b, void *c)
{
    ARG_UNUSED(a);
    ARG_UNUSED(b);
    ARG_UNUSED(c);
    for (;;) {
        k_sem_take(&tx_job, K_FOREVER);
        struct link_tx_result r = {0};
        struct bt_conn *conn = conn_get();
        marker_on(MARKER_TX);
        r.status = conn == NULL ? LINK_TX_NOTCONN : transfer(conn, &r);
        marker_off(MARKER_TX);
        if (conn != NULL) {
            bt_conn_unref(conn);
        }
        if (r.status != LINK_TX_DONE) {
            r.done_ms = k_uptime_get_32();
        }
        k_spinlock_key_t key = k_spin_lock(&lock);
        tx_result = r;
        tx_result_ready = true;
        k_spin_unlock(&lock, key);
        atomic_set(&tx_busy, 0);
        wake();
    }
}

K_THREAD_DEFINE(i1_tx, TX_THREAD_STACK, tx_thread, NULL, NULL, NULL, TX_THREAD_PRIORITY, 0, 0);

int link_send(const uint8_t *frame, uint16_t length, uint8_t stream)
{
    if (length < FRAG_MIN_FRAME || length > FRAG_MAX_FRAME) {
        return -EINVAL;   /* §4.1: never send an oversize or truncated frame */
    }
    if (!atomic_cas(&tx_busy, 0, 1)) {
        return -EBUSY;
    }
    tx_frame = frame;
    tx_length = length;
    tx_stream = stream;
    k_sem_give(&tx_job);
    return 0;
}

bool link_tx_busy(void)
{
    return atomic_get(&tx_busy) != 0;
}

bool link_tx_take_result(struct link_tx_result *result)
{
    k_spinlock_key_t key = k_spin_lock(&lock);
    const bool ready = tx_result_ready;
    if (ready) {
        *result = tx_result;
        tx_result_ready = false;
    }
    k_spin_unlock(&lock, key);
    return ready;
}

void link_rx_configure(uint8_t stream_mask)
{
    k_spinlock_key_t key = k_spin_lock(&lock);
    rx.stream_mask = stream_mask;
    k_spin_unlock(&lock, key);
}

bool link_rx_take(const uint8_t **frame, uint16_t *length, uint8_t *stream)
{
    k_spinlock_key_t key = k_spin_lock(&lock);
    const bool pending = rx.pending;
    if (pending) {
        *frame = rx.buffer;
        *length = rx.pending_length;
        *stream = rx.pending_stream;
    }
    k_spin_unlock(&lock, key);
    return pending;
}

void link_rx_release(void)
{
    k_spinlock_key_t key = k_spin_lock(&lock);
    reasm_release(&rx);
    k_spin_unlock(&lock, key);
}

void link_rx_tick(uint32_t now_ms)
{
    k_spinlock_key_t key = k_spin_lock(&lock);
    reasm_tick(&rx, now_ms);
    k_spin_unlock(&lock, key);
}

void link_rx_counters(uint32_t out[REASM_COUNTER_COUNT])
{
    k_spinlock_key_t key = k_spin_lock(&lock);
    memcpy(out, rx.counters, sizeof(rx.counters));
    k_spin_unlock(&lock, key);
}

void link_rx_reset_counters(void)
{
    k_spinlock_key_t key = k_spin_lock(&lock);
    reasm_reset_counters(&rx);
    info.rx_writes = 0;
    info.rx_bytes = 0;
    info.notifications = 0;
    k_spin_unlock(&lock, key);
}

int link_init(void)
{
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    reasm_init(&rx, rx_buffer, sizeof(rx_buffer),
               (1U << FRAG_STREAM_I1) | (1U << FRAG_STREAM_ECHO), FRAG_REASSEMBLY_TIMEOUT_MS);
    k_work_init(&adv_work, adv_start);
    bt_gatt_cb_register(&gatt_callbacks);
    const int err = bt_enable(NULL);
    if (err == 0) {
        k_work_submit(&adv_work);
    }
    return err;
}
