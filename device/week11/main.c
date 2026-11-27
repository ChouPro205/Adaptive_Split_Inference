/*
 * Week 11 Device firmware, link-state measurements for the week 12 lab (W11-D2, W11-D3; criteria TC4 in the
 * week 11 plan until the week 11 report). Fork of week10/main.c (hash-locked) with the head/I1 cycle replaced
 * by the link ops of link_cycle.c (STATE, IDLE, ECHO, S0C, RECONNECT; week11_link_plan.h, one session per
 * build).
 *
 * link-usb  USB CDC + BLE: VERIFY (S0c of the 100 W8-D3 inputs + plan digest; no link needed), STATE <i>,
 *           STATEX <phy> <interval> <latency> <octets> <dbm>, ECHO <len> <flags> [n], IDLE <ms>,
 *           S0C <n> <repeat>, RECONNECT, LATENCY <mode>, RSSI, SESSION [first] [count] (dry run of the plan
 *           against the KV260, every entry printed), MARKERS. Powered by the laptop: its timings are debug
 *           evidence only, never energy numbers.
 * link      no USB/console/LED/NVS: at power-on runs the PPK2 session by itself:
 *           plan self-check -> self-test D0..D4 -> idle with the radio off -> BLE, link ready -> settle ->
 *           connected idle -> every plan entry -> stop and stay off-air (W8-D2).
 */
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include <cmsis_core.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/util.h>

#include "ble_link.h"
#include "link_cycle.h"
#include "marker_ctrl.h"
#include "markers.h"
#include "s0c.h"
#include "sha256.h"
#include "week11_build.h"

#if !defined(CONFIG_BT)
#error "Week 11 link images need the radio (W11-D3)"
#endif

#if defined(CONFIG_WEEK11_LINK_USB)
#define WEEK11_CONSOLE 1
#include <zephyr/drivers/uart.h>
#include <zephyr/sys/reboot.h>
BUILD_ASSERT(DT_NODE_HAS_COMPAT(DT_CHOSEN(zephyr_console), zephyr_cdc_acm_uart),
	     "USB variants use USB CDC ACM as control/debug console");
static const struct device *const console_device = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));
#else
#define WEEK11_CONSOLE 0
BUILD_ASSERT(!IS_ENABLED(CONFIG_PRINTK) && !IS_ENABLED(CONFIG_USB_DEVICE_STACK_NEXT) &&
	     !IS_ENABLED(CONFIG_SERIAL), "link image: no USB, console or printk");
#endif

#define CPU_HZ 64000000u

/* Kept in every image (check_week11_build.py: build_id_in_image), also without a console. */
static const char build_id[] = "WEEK11_BUILD_ID=" WEEK11_BUILD_ID;

static void dwt_init(void)
{
	CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
	DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

/* ------------------------------------------------------------------ markers / LEDs */

#define LED_SPEC(n) GPIO_DT_SPEC_GET(DT_ALIAS(led##n), gpios)
static const struct gpio_dt_spec leds[] = {LED_SPEC(0), LED_SPEC(1), LED_SPEC(2), LED_SPEC(3)};

static void leds_off(void)
{
	for (size_t i = 0; i < ARRAY_SIZE(leds); ++i) {
		if (gpio_is_ready_dt(&leds[i])) {
			(void)gpio_pin_configure_dt(&leds[i], GPIO_OUTPUT_INACTIVE);
		}
	}
}

/* TC1 of week 7: D0 HEAD, D1 (LINK in week 11), D2 TX, D3 WAIT, D4 CTRL, one after another. */
static void markers_selftest(void)
{
	for (unsigned m = 0; m < 5u; ++m) {
		if (m < 4u) {
			marker_on((enum marker_id)m);
		} else {
			marker_ctrl_on();
		}
		k_msleep(CONFIG_WEEK11_SELFTEST_MS);
		if (m < 4u) {
			marker_off((enum marker_id)m);
		} else {
			marker_ctrl_off();
		}
	}
}

static bool plan_ok(void)
{
	char hex[65];
	link_plan_digest(hex);
	return strcmp(hex, link_plan_sha256()) == 0;
}

#if !defined(CONFIG_WEEK11_LINK_USB)
static void wait_link_ready(void)
{
	while (!link_ready()) {
		(void)k_sem_take(&link_wake, K_MSEC(500));
	}
	/* Give the central's ATT MTU exchange time to reach 247 (week 10). */
	for (unsigned i = 0; i < 50u && link_mtu() < CONFIG_BT_L2CAP_TX_MTU; ++i) {
		k_msleep(100);
	}
}
#endif

/* ------------------------------------------------------------------ console (link-usb) */

#if WEEK11_CONSOLE
#define LINE_MAX 96
#define MAX_ARGS 7
static char line[LINE_MAX];
static unsigned line_length;
static bool line_discard;

static void pace(void)
{
	k_msleep(3);   /* keep the CDC TX FIFO from overflowing on long dumps (week 3/5 lesson) */
}

static bool console_line(void)
{
	unsigned char byte;
	while (uart_poll_in(console_device, &byte) == 0) {
		if (byte == '\n') {
			line[line_length] = '\0';
			const bool ok = !line_discard;
			line_length = 0;
			line_discard = false;
			if (ok) {
				return true;
			}
			printk("ERROR line too long\r\n");
		} else if (byte != '\r' && !line_discard) {
			if (byte == '\0' || line_length + 1U >= sizeof(line)) {
				line_discard = true;
			} else {
				line[line_length++] = (char)byte;
			}
		}
	}
	return false;
}

static int split_args(char *text, char *argv[MAX_ARGS])
{
	int argc = 0;
	char *save = NULL;
	for (char *tok = strtok_r(text, " ", &save); tok != NULL && argc < MAX_ARGS;
	     tok = strtok_r(NULL, " ", &save)) {
		argv[argc++] = tok;
	}
	return argc;
}

static bool parse_u32(const char *text, uint32_t *out)
{
	char *end = NULL;
	const unsigned long value = strtoul(text, &end, 0);
	if (text[0] == '\0' || end == NULL || *end != '\0') {
		return false;
	}
	*out = (uint32_t)value;
	return true;
}

static bool parse_i32(const char *text, int32_t *out)
{
	char *end = NULL;
	const long value = strtol(text, &end, 0);
	if (text[0] == '\0' || end == NULL || *end != '\0') {
		return false;
	}
	*out = (int32_t)value;
	return true;
}

#define STATS_MAX_THREADS 16
struct thread_stat {
	const char *name;
	size_t size;
	size_t unused;
};
static struct thread_stat stats[STATS_MAX_THREADS];
static unsigned stats_count;

static void collect_thread(const struct k_thread *thread, void *user_data)
{
	ARG_UNUSED(user_data);
	size_t unused = 0;
	if (stats_count >= STATS_MAX_THREADS || k_thread_stack_space_get(thread, &unused) != 0) {
		return;
	}
	const char *name = k_thread_name_get((k_tid_t)thread);
	stats[stats_count++] = (struct thread_stat){
		.name = (name != NULL && name[0] != '\0') ? name : "?",
		.size = thread->stack_info.size,
		.unused = unused,
	};
}

static void print_stacks(void)
{
	stats_count = 0;
	k_thread_foreach(collect_thread, NULL);
	for (unsigned i = 0; i < stats_count; ++i) {
		printk("STACK %s used=%u size=%u\r\n", stats[i].name,
		       (unsigned)(stats[i].size - stats[i].unused), (unsigned)stats[i].size);
	}
}

static void print_result(const struct link_result *r)
{
	const uint32_t us = CPU_HZ / 1000000u;
	printk("OP i=%u op=%s state=%u a=%u b=%u res=%s ctrl_us=%u link_ms=%u interval_1250us=%u latency=%u "
	       "timeout_10ms=%u phy_tx=%u phy_rx=%u tx_len=%u tx_dbm=%d hci_err=%d rid=%u len=%u frags=%u "
	       "mtu=%u enomem=%u tx_us=%u wait_us=%u invalid=%u body=%u k=%u head_us=%u\r\n",
	       r->index, r->op < LINK_OP_COUNT ? link_op_names[r->op] : "?", r->state, r->a, r->b,
	       link_error_names[r->error], r->ctrl_cycles / us, r->link_ms, r->interval_1250us, r->latency,
	       r->timeout_10ms, r->tx_phy, r->rx_phy, r->tx_data_len, r->tx_power_dbm, r->hci_err,
	       r->request_id, r->frame_length, r->fragments, r->att_mtu, r->enomem_retries, r->tx_cycles / us,
	       r->wait_cycles / us, r->invalid_answers, r->body_len, r->rice_k, r->head_cycles / us);
}

static void print_link(void)
{
	struct link_info li;
	int8_t rssi = 0;
	link_get_info(&li);
	const int rssi_err = li.connected ? link_read_rssi(&rssi) : -1;
	printk("LINK connected=%u ready=%u att_mtu=%u interval_1250us=%u latency=%u timeout_10ms=%u "
	       "phy_tx=%u phy_rx=%u tx_len=%u rx_len=%u tx_dbm=%d latency_mode=%u rssi=%d rssi_err=%d "
	       "connections=%u disconnections=%u reason=0x%02x param_updates=%u phy_updates=%u "
	       "len_updates=%u\r\n",
	       li.connected, link_ready(), li.att_mtu, li.interval_1250us, li.latency, li.timeout_10ms,
	       li.tx_phy, li.rx_phy, li.tx_data_len, li.rx_data_len, li.tx_power_dbm, li.latency_mode, rssi,
	       rssi_err, li.connections, li.disconnections, li.last_disconnect_reason, li.param_updates,
	       li.phy_updates, li.data_len_updates);
}

/* TC4: S0c of every W8-D3 input (body, FP16 scale, k) for the host check against s0c_v1_ref.py. */
static void verify_s0c(void)
{
	for (unsigned n = 0; n < link_sample_count(); ++n) {
		uint8_t body[S0C_BODY_MAX], scale[2], k = 0;
		uint16_t length = 0;
		char hex[2u * S0C_BODY_MAX + 1u];
		if (link_s0c_of(n, body, &length, scale, &k) != 0) {
			printk("VS0C n=%u ERROR\r\n", n);
			continue;
		}
		for (unsigned i = 0; i < length; ++i) {
			static const char digits[] = "0123456789abcdef";
			hex[2u * i] = digits[body[i] >> 4];
			hex[2u * i + 1u] = digits[body[i] & 15u];
		}
		hex[2u * length] = '\0';
		printk("VS0C n=%u body_len=%u k=%u scale=%02x%02x body=%s\r\n", n, length, k, scale[0], scale[1],
		       hex);
		pace();
	}
}

static void print_banner(void)
{
	char hex[65];
	link_plan_digest(hex);
	printk("READY WEEK11 build=%s variant=%s session=%u states=%u entries=%u samples=%u s0c=%s "
	       "boot_idle_s=%u connected_idle_s=%u settle_s=%u ctrl_min_us=%u state_timeout_ms=%u "
	       "state_settle_ms=%u echo_timeout_ms=%u reconnect_timeout_ms=%u op_gap_ms=%u d4_pin=P0.%u "
	       "set_sha256=%s plan_sha256=%s plan_device_sha256=%s plan_ok=%u\r\n",
	       WEEK11_BUILD_ID, WEEK11_VARIANT, WEEK11_SESSION, link_states(), link_plan_entries(),
	       link_sample_count(), S0C_VERSION, CONFIG_WEEK11_BOOT_IDLE_S, CONFIG_WEEK11_CONNECTED_IDLE_S,
	       CONFIG_WEEK11_SETTLE_S, CONFIG_WEEK11_CTRL_MIN_US, CONFIG_WEEK11_STATE_TIMEOUT_MS,
	       CONFIG_WEEK11_STATE_SETTLE_MS, CONFIG_WEEK11_ECHO_TIMEOUT_MS, CONFIG_WEEK11_RECONNECT_TIMEOUT_MS,
	       CONFIG_WEEK11_OP_GAP_MS, MARKER_CTRL_PIN, link_set_sha256(), link_plan_sha256(), hex,
	       strcmp(hex, link_plan_sha256()) == 0);
	print_link();
}

static void print_help(void)
{
	printk("COMMANDS HELP | STATUS | STACK | MARKERS | REBOOT | VERIFY | RSSI | LATENCY <0|1|2>\r\n");
	printk("COMMANDS STATE <i> | STATEX <phy 1|2|3> <interval> <latency> <octets 27|251> <dbm>\r\n");
	printk("COMMANDS ECHO <len> <flags> [n] | IDLE <ms> | S0C <n> <repeat> | RECONNECT\r\n");
	printk("COMMANDS SESSION [first] [count]\r\n");
}
#endif /* WEEK11_CONSOLE */

/* ------------------------------------------------------------------ session */

/* Entries first .. first + count - 1. Returns the entries that ended OK. Every entry runs connected (S0C
 * too: the base block), so a lost link is waited for first, at most 30 s, as week 10. */
static unsigned run_plan(unsigned first, unsigned count, bool verbose)
{
	unsigned ok = 0;
	for (unsigned i = first; i < first + count && i < link_plan_entries(); ++i) {
		struct link_result r;
		for (unsigned waited = 0; !link_ready() && waited < 300u; ++waited) {
			(void)k_sem_take(&link_wake, K_MSEC(100));
		}
		link_run_entry(i, &r);
		ok += r.error == LINK_OK;
#if WEEK11_CONSOLE
		if (verbose) {
			print_result(&r);
		}
#else
		ARG_UNUSED(verbose);
#endif
		if (r.op == LINK_OP_ECHO || r.op == LINK_OP_S0C || r.op == LINK_OP_RECONNECT) {
			k_msleep(CONFIG_WEEK11_OP_GAP_MS);
		}
	}
	return ok;
}

#if !WEEK11_CONSOLE
static void session_after_idle(void)
{
	wait_link_ready();
	k_sleep(K_SECONDS(CONFIG_WEEK11_SETTLE_S));
	k_sleep(K_SECONDS(CONFIG_WEEK11_CONNECTED_IDLE_S));
	(void)run_plan(0, link_plan_entries(), false);
	(void)link_disconnect();
}
#endif

#if WEEK11_CONSOLE
static void dispatch(void)
{
	char *argv[MAX_ARGS];
	const int argc = split_args(line, argv);
	uint32_t a = 0, b = 0, c = 0, d = 0;
	int32_t e = 0;
	struct link_result r;
	if (argc == 0) {
		return;
	}
	const char *cmd = argv[0];
	if (strcmp(cmd, "HELP") == 0) {
		print_help();
	} else if (strcmp(cmd, "STATUS") == 0) {
		print_banner();
	} else if (strcmp(cmd, "STACK") == 0) {
		print_stacks();
	} else if (strcmp(cmd, "MARKERS") == 0) {
		markers_selftest();
		printk("MARKERS END order=D0,D1,D2,D3,D4 width_ms=%u\r\n", CONFIG_WEEK11_SELFTEST_MS);
	} else if (strcmp(cmd, "REBOOT") == 0) {
		printk("REBOOT\r\n");
		k_msleep(100);
		sys_reboot(SYS_REBOOT_COLD);
	} else if (strcmp(cmd, "VERIFY") == 0 && argc == 1) {
		char hex[65];
		verify_s0c();
		link_plan_digest(hex);
		printk("VERIFY END samples=%u s0c=%s set_sha256=%s plan_sha256=%s plan_device_sha256=%s plan_ok=%u\r\n",
		       link_sample_count(), S0C_VERSION, link_set_sha256(), link_plan_sha256(), hex,
		       strcmp(hex, link_plan_sha256()) == 0);
	} else if (strcmp(cmd, "RSSI") == 0) {
		print_link();
	} else if (strcmp(cmd, "LATENCY") == 0 && argc == 2 && parse_u32(argv[1], &a) && a <= 2u) {
		printk("LATENCY mode=%u err=%d\r\n", a, link_set_latency_mode((uint8_t)a));
	} else if (strcmp(cmd, "STATE") == 0 && argc == 2 && parse_u32(argv[1], &a) && a < link_states()) {
		link_run_op(LINK_OP_STATE, (uint8_t)a, 0, 0, &r);
		print_result(&r);
	} else if (strcmp(cmd, "STATEX") == 0 && argc == 6 && parse_u32(argv[1], &a) && a >= 1u && a <= 3u &&
		   parse_u32(argv[2], &b) && b >= 6u && b <= 3200u && parse_u32(argv[3], &c) && c <= 499u &&
		   parse_u32(argv[4], &d) && (d == 27u || d == 251u) && parse_i32(argv[5], &e) && e >= -40 &&
		   e <= 8) {
		link_run_state_values((uint8_t)a, (uint16_t)b, (uint16_t)c, (uint8_t)d, (int8_t)e, &r);
		print_result(&r);
	} else if (strcmp(cmd, "ECHO") == 0 && (argc == 3 || argc == 4) && parse_u32(argv[1], &a) &&
		   a >= 36u && a <= 6380u && parse_u32(argv[2], &b) && b <= 3u &&
		   (argc == 3 || (parse_u32(argv[3], &c) && c >= 1u && c <= 1000u))) {
		const unsigned n = argc == 4 ? c : 1u;
		unsigned ok = 0;
		for (unsigned i = 0; i < n; ++i) {
			link_run_op(LINK_OP_ECHO, LINK_BASE_STATE, (uint16_t)a, (uint16_t)b, &r);
			r.index = i;
			ok += r.error == LINK_OK;
			print_result(&r);
			k_msleep(CONFIG_WEEK11_OP_GAP_MS);
		}
		printk("ECHO END len=%u flags=%u n=%u ok=%u\r\n", a, b, n, ok);
	} else if (strcmp(cmd, "IDLE") == 0 && argc == 2 && parse_u32(argv[1], &a) && a <= 65535u) {
		link_run_op(LINK_OP_IDLE, LINK_BASE_STATE, (uint16_t)a, 0, &r);
		print_result(&r);
	} else if (strcmp(cmd, "S0C") == 0 && argc == 3 && parse_u32(argv[1], &a) && a < link_sample_count() &&
		   parse_u32(argv[2], &b) && b >= 1u && b <= 10000u) {
		link_run_op(LINK_OP_S0C, LINK_BASE_STATE, (uint16_t)a, (uint16_t)b, &r);
		print_result(&r);
	} else if (strcmp(cmd, "RECONNECT") == 0 && argc == 1) {
		link_run_op(LINK_OP_RECONNECT, LINK_BASE_STATE, 0, 0, &r);
		print_result(&r);
		print_link();
	} else if (strcmp(cmd, "SESSION") == 0 && argc <= 3) {
		a = 0;
		b = link_plan_entries();
		if ((argc < 2 || parse_u32(argv[1], &a)) && (argc < 3 || parse_u32(argv[2], &b)) &&
		    a < link_plan_entries() && b >= 1u && b <= link_plan_entries() - a) {
			if (!plan_ok()) {
				printk("ERROR plan bytes differ from plan_sha256\r\n");
				return;
			}
			if (!link_ready()) {
				printk("ERROR link not ready (start the edge peer)\r\n");
				return;
			}
			printk("SESSION BEGIN first=%u count=%u plan_sha256=%s\r\n", a, b, link_plan_sha256());
			const unsigned ok = run_plan(a, b, true);
			print_link();
			print_stacks();
			printk("SESSION END first=%u count=%u ok=%u failed=%u\r\n", a, b, ok, b - ok);
		} else {
			printk("ERROR usage SESSION [first] [count]\r\n");
		}
	} else {
		printk("ERROR unknown command or arguments (HELP)\r\n");
	}
}
#endif /* WEEK11_CONSOLE */

/* ------------------------------------------------------------------ main */

int main(void)
{
	if (markers_init() != 0 || marker_ctrl_init() != 0) {
		return -1;
	}
	leds_off();
	dwt_init();
	__asm__ volatile("" : : "r"(build_id) : "memory");

#if defined(CONFIG_WEEK11_LINK)
	k_msleep(100);
	if (!plan_ok()) {
		/* Plan bytes differ from WEEK11_LINK_PLAN_SHA256: no session. Ten 5 ms CTRL pulses mark it. */
		for (unsigned i = 0; i < 10u; ++i) {
			marker_ctrl_on();
			k_msleep(5);
			marker_ctrl_off();
			k_msleep(45);
		}
		k_sleep(K_FOREVER);
	}
	markers_selftest();
	k_sleep(K_SECONDS(CONFIG_WEEK11_BOOT_IDLE_S));   /* W7-D3: idle window, radio off */
	if (link_init() != 0) {
		k_sleep(K_FOREVER);
	}
	link_cycle_init();   /* after link_init(): it resets the reassembler's stream mask */
	session_after_idle();
	k_sleep(K_FOREVER);
	return 0;
#else
	if (!device_is_ready(console_device)) {
		return -1;
	}
	struct uart_config config = {
		.baudrate = 115200, .parity = UART_CFG_PARITY_NONE, .stop_bits = UART_CFG_STOP_BITS_1,
		.data_bits = UART_CFG_DATA_BITS_8, .flow_ctrl = UART_CFG_FLOW_CTRL_RTS_CTS,
	};
	if (uart_configure(console_device, &config) != 0) {
		return -1;
	}
	uart_irq_rx_enable(console_device);   /* week 3 lesson: arm USB OUT */
	const int bt_err = link_init();
	link_cycle_init();   /* after link_init(): it resets the reassembler's stream mask */
	bool connected_before = false;
	for (;;) {
		uint32_t dtr = 0;
		const bool connected =
			uart_line_ctrl_get(console_device, UART_LINE_CTRL_DTR, &dtr) == 0 && dtr;
		if (connected && !connected_before) {
			k_msleep(100);
			print_banner();
			printk("BOOT bt_enable=%d plan_ok=%u\r\n", bt_err, plan_ok());
			print_help();
			line_length = 0;
			line_discard = false;
		}
		if (connected && console_line()) {
			dispatch();
			memset(line, 0, sizeof(line));
		}
		connected_before = connected;
		k_msleep(10);
	}
	return 0;
#endif
}
