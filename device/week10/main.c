/*
 * Week 10 Device firmware, radio-on cycle at every s (decision W10-D4, criteria TC1/TC2/TC7 in the week 10
 * plan until the week 10 report). Fork of week8/main.c (hash-locked) without the NVS nonce store and
 * I2: rho0 only, the cycle is ble_cycle.c at the split of the W10-D4 plan (week10_ble_plan.h, 50 rounds x
 * a permutation of s0..s10, round k = W8-D3 sample k); s10 runs the whole model on the dongle.
 *
 * ble-usb  USB CDC + BLE: VERIFY ALL | VERIFY <s> (q/scale SHA-256 of the 50 samples, the plain request
 *          of every s <= 9, the s10 logits and label; no link needed), ONE <n> <s>, SESSION [gap_ms]
 *          [first] [count] (dry run of the plan against the KV260, every cycle printed), CONNPARAM,
 *          MARKERS. Powered by the laptop: its timings are debug evidence only, never energy numbers.
 * ble      no USB/console/LED, no NVS: at power-on runs the PPK2 session by itself:
 *          plan self-check -> self-test D0..D4 -> idle with the radio off -> BLE, link + parameters ->
 *          connected idle -> 550 plan cycles, CONFIG_WEEK10_CYCLE_GAP_MS apart -> stop and stay
 *          off-air (week8/ble_link.c, W8-D2).
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

#include "ble_cycle.h"
#include "ble_link.h"
#include "frag.h"
#include "marker_ctrl.h"
#include "markers.h"
#include "sha256.h"
#include "week10_build.h"

#if !defined(CONFIG_BT)
#error "Week 10 ble images need the radio (W10-D4)"
#endif

#if defined(CONFIG_WEEK10_BLE_USB)
#define WEEK10_CONSOLE 1
#include <zephyr/drivers/uart.h>
#include <zephyr/sys/reboot.h>
BUILD_ASSERT(DT_NODE_HAS_COMPAT(DT_CHOSEN(zephyr_console), zephyr_cdc_acm_uart),
	     "USB variants use USB CDC ACM as control/debug console");
static const struct device *const console_device = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));
#else
#define WEEK10_CONSOLE 0
BUILD_ASSERT(!IS_ENABLED(CONFIG_PRINTK) && !IS_ENABLED(CONFIG_USB_DEVICE_STACK_NEXT) &&
	     !IS_ENABLED(CONFIG_SERIAL), "ble image: no USB, console or printk (TC1)");
#endif

#define KERNEL_NAME "FAST"
#define CPU_HZ 64000000u

/* Kept in every image (check_week10_build.py: build_id_in_image), also without a console. */
static const char build_id[] = "WEEK10_BUILD_ID=" WEEK10_BUILD_ID;

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

/* TC1 of week 7: D0 HEAD, D1 PROT, D2 TX, D3 WAIT, D4 CTRL, one after another, back to back. */
static void markers_selftest(void)
{
	for (unsigned m = 0; m < 5u; ++m) {
		if (m < 4u) {
			marker_on((enum marker_id)m);
		} else {
			marker_ctrl_on();
		}
		k_msleep(CONFIG_WEEK10_SELFTEST_MS);
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
	ble_plan_digest(hex);
	return strcmp(hex, ble_plan_sha256()) == 0;
}

/* ------------------------------------------------------------------ console (ble-usb) */

#if WEEK10_CONSOLE
#define LINE_MAX 96
#define MAX_ARGS 6
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

static void logits_hex(const float logits[G2_LOGITS], uint32_t bits[G2_LOGITS])
{
	memcpy(bits, logits, G2_LOGITS * sizeof(uint32_t));
}

static void print_cycle(const struct ble_result *r)
{
	const uint32_t us = CPU_HZ / 1000000u;
	uint32_t bits[G2_LOGITS];
	logits_hex(r->logits, bits);
	printk("CYCLE i=%u round=%u n=%u id=%s s=%u rho=%u k=%u bytes=%u rid=%u len=%u frags=%u mtu=%u "
	       "ctrl_us=%u head_us=%u quant_us=%u enc_us=%u tx_us=%u wait_us=%u enomem=%u invalid=%u "
	       "status=%u res=%s logits=%08x,%08x,%08x,%08x,%08x label=%u\r\n",
	       r->cycle, r->cycle / BLE_SPLITS, r->sample, ble_sample_id(r->sample), r->split, r->rho,
	       r->k, r->bytes_payload, r->request_id, r->frame_length, r->fragments, r->att_mtu,
	       r->ctrl_cycles / us, r->head_cycles / us, r->quant_cycles / us, r->encode_cycles / us,
	       r->tx_cycles / us, r->wait_cycles / us, r->enomem_retries, r->invalid_responses,
	       r->response_status, ble_error_names[r->error], bits[0], bits[1], bits[2], bits[3],
	       bits[4], r->label);
}
#endif /* WEEK10_CONSOLE */

/* ------------------------------------------------------------------ session */

/* Cycles first .. first + count - 1 of the W10-D4 plan, gap_ms apart. Returns the cycles that ended OK. */
static unsigned run_plan(unsigned first, unsigned count, uint32_t gap_ms, bool verbose)
{
	unsigned ok = 0;
	for (unsigned i = first; i < first + count && i < ble_plan_cycles(); ++i) {
		struct ble_result r;
		if (ble_plan_split(i) != BLE_DEVICE_ONLY_SPLIT) {
			for (unsigned waited = 0; !link_ready() && waited < 300u; ++waited) {
				(void)k_sem_take(&link_wake, K_MSEC(100));   /* reconnect: at most 30 s */
			}
		}
		ble_cycle_run_plan(i, &r);
		ok += r.error == BLE_OK;
#if WEEK10_CONSOLE
		if (verbose) {
			print_cycle(&r);
		}
#else
		ARG_UNUSED(verbose);
#endif
		k_msleep(gap_ms);
	}
	return ok;
}

#if !WEEK10_CONSOLE
static void wait_link_ready(void)
{
	while (!link_ready()) {
		(void)k_sem_take(&link_wake, K_MSEC(500));
	}
	/* Windows centrals start the ATT MTU exchange themselves; give it time to reach 247. */
	for (unsigned i = 0; i < 50u && link_mtu() < CONFIG_BT_L2CAP_TX_MTU; ++i) {
		k_msleep(100);
	}
}

/* The part of the energy session after the radio-off idle window (link_init already called). */
static void session_after_idle(bool verbose)
{
	wait_link_ready();
	if (CONFIG_WEEK10_CONN_INTERVAL_1250US > 0) {
		/* W7-D7: latency 0, supervision timeout 4 s; the central decides (EVT CONN_PARAM). */
		(void)link_request_conn_params(CONFIG_WEEK10_CONN_INTERVAL_1250US,
					       CONFIG_WEEK10_CONN_INTERVAL_1250US, 0, 400);
	}
	k_sleep(K_SECONDS(CONFIG_WEEK10_SETTLE_S));
	k_sleep(K_SECONDS(CONFIG_WEEK10_CONNECTED_IDLE_S));
	(void)run_plan(0, ble_plan_cycles(), CONFIG_WEEK10_CYCLE_GAP_MS, verbose);
	(void)link_disconnect();
}
#endif

#if WEEK10_CONSOLE
static void hex_digest(const void *data, size_t length, char out[65])
{
	uint8_t digest[32];
	sha256(data, length, digest);
	sha256_hex(digest, out);
}

static void print_link(void)
{
	struct link_info li;
	link_get_info(&li);
	printk("LINK connected=%u ready=%u att_mtu=%u interval_1250us=%u latency=%u timeout_10ms=%u "
	       "phy_tx=%u phy_rx=%u connections=%u disconnections=%u\r\n",
	       li.connected, link_ready(), li.att_mtu, li.interval_1250us, li.latency,
	       li.timeout_10ms, li.tx_phy, li.rx_phy, li.connections, li.disconnections);
}

/* TC2: q/scale of the 50 samples at one split vs the host references (week 9 refs.csv, the week 10
 * refs sent to the KV260); s <= 9: the plain request (request_id n + 1) vs the Python reference;
 * s10: the FP32 logits and the label computed on the dongle vs the host shim. */
static void verify_split(unsigned split)
{
	static uint8_t frame[FRAG_MAX_FRAME];
	for (unsigned n = 0; n < ble_sample_count(); ++n) {
		struct ble_tensor t;
		char q_hex[65], s_hex[65], r_hex[65];
		if (ble_head(split, n, &t, NULL) != 0) {
			printk("VQ n=%u s=%u ERROR\r\n", n, split);
			continue;
		}
		hex_digest(t.q, (size_t)t.channels * t.length, q_hex);
		hex_digest(t.scale_le, 2u * t.channels, s_hex);
		printk("VQ n=%u id=%s s=%u C=%u L=%u bytes=%u q_sha256=%s scale_sha256=%s\r\n", n,
		       ble_sample_id(n), split, t.channels, t.length,
		       (unsigned)(t.channels * t.length + 2u * t.channels), q_hex, s_hex);
		pace();
		if (split == BLE_DEVICE_ONLY_SPLIT) {
			float logits[G2_LOGITS];
			uint32_t bits[G2_LOGITS];
			memcpy(logits, t.values, sizeof(logits));
			logits_hex(logits, bits);
			printk("VLAB n=%u s=%u logits=%08x,%08x,%08x,%08x,%08x label=%u\r\n", n, split,
			       bits[0], bits[1], bits[2], bits[3], bits[4], g2_label(logits));
		} else {
			const size_t len = ble_request(&t, n + 1u, frame);
			hex_digest(frame, len, r_hex);
			printk("VREQ n=%u s=%u rho=P0 rid=%u len=%u sha256=%s\r\n", n, split, n + 1u,
			       (unsigned)len, r_hex);
		}
		pace();
	}
}

/* ------------------------------------------------------------------ banner / dispatch */

static void print_banner(void)
{
	char hex[65];
	ble_plan_digest(hex);
	printk("READY WEEK10 build=%s variant=%s kernel=%s rounds=%u splits=%u cycles=%u samples=%u "
	       "gap_ms=%u boot_idle_s=%u connected_idle_s=%u ctrl_min_us=%u selftest_ms=%u timeout_ms=%u "
	       "conn_interval_1250us=%u d4_pin=P0.%u set_sha256=%s plan_sha256=%s plan_device_sha256=%s "
	       "plan_ok=%u\r\n",
	       WEEK10_BUILD_ID, WEEK10_VARIANT, KERNEL_NAME, ble_sample_count(), BLE_SPLITS,
	       ble_plan_cycles(), ble_sample_count(), CONFIG_WEEK10_CYCLE_GAP_MS,
	       CONFIG_WEEK10_BOOT_IDLE_S, CONFIG_WEEK10_CONNECTED_IDLE_S, CONFIG_WEEK10_CTRL_MIN_US,
	       CONFIG_WEEK10_SELFTEST_MS, CONFIG_WEEK10_RESPONSE_TIMEOUT_MS,
	       CONFIG_WEEK10_CONN_INTERVAL_1250US, MARKER_CTRL_PIN, ble_set_sha256(), ble_plan_sha256(),
	       hex, strcmp(hex, ble_plan_sha256()) == 0);
	print_link();
}

static void print_help(void)
{
	printk("COMMANDS HELP | STATUS | STACK | MARKERS | REBOOT | CONNPARAM <min> <max>\r\n");
	printk("COMMANDS VERIFY ALL | VERIFY <s> | ONE <n> <s> | SESSION [gap_ms] [first] [count]\r\n");
}

static bool parse_split(const char *text, uint32_t *split)
{
	return parse_u32(text, split) && *split < BLE_SPLITS;
}

/* Cycles that send a request need the KV260 connected and subscribed. */
static bool plan_needs_link(unsigned first, unsigned count)
{
	for (unsigned i = first; i < first + count && i < ble_plan_cycles(); ++i) {
		if (ble_plan_split(i) != BLE_DEVICE_ONLY_SPLIT) {
			return true;
		}
	}
	return false;
}

static void dispatch(void)
{
	char *argv[MAX_ARGS];
	const int argc = split_args(line, argv);
	uint32_t a = 0, b = 0, c = 0;
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
		printk("MARKERS END order=D0,D1,D2,D3,D4 width_ms=%u\r\n", CONFIG_WEEK10_SELFTEST_MS);
	} else if (strcmp(cmd, "REBOOT") == 0) {
		printk("REBOOT\r\n");
		k_msleep(100);
		sys_reboot(SYS_REBOOT_COLD);
	} else if (strcmp(cmd, "CONNPARAM") == 0 && argc == 3) {
		if (parse_u32(argv[1], &a) && parse_u32(argv[2], &b) && a >= 6u && a <= b && b <= 3200u) {
			printk("CONNPARAM request min_1250us=%u max_1250us=%u err=%d\r\n", a, b,
			       link_request_conn_params((uint16_t)a, (uint16_t)b, 0, 400));
		} else {
			printk("ERROR usage CONNPARAM <min> <max> (units of 1.25 ms, 6..3200)\r\n");
		}
	} else if (strcmp(cmd, "VERIFY") == 0 && argc == 2 &&
		   (strcmp(argv[1], "ALL") == 0 || parse_split(argv[1], &a))) {
		const bool all = strcmp(argv[1], "ALL") == 0;
		for (unsigned s = all ? 0u : a; s < (all ? BLE_SPLITS : a + 1u); ++s) {
			verify_split(s);
		}
		printk("VERIFY END kernel=%s samples=%u splits=%s set_sha256=%s\r\n", KERNEL_NAME,
		       ble_sample_count(), all ? "ALL" : argv[1], ble_set_sha256());
	} else if (strcmp(cmd, "ONE") == 0) {
		/* One rho0 cycle of sample n at split s (s <= 9 over the link). */
		if (argc == 3 && parse_u32(argv[1], &a) && a < ble_sample_count() &&
		    parse_split(argv[2], &b)) {
			if (b != BLE_DEVICE_ONLY_SPLIT && !link_ready()) {
				printk("ERROR link not ready (start the edge peer)\r\n");
				return;
			}
			struct ble_result r;
			printk("ONE BEGIN n=%u s=%u\r\n", a, b);
			ble_cycle_run(b, a, &r);
			print_cycle(&r);
			printk("ONE END ok=%u\r\n", r.error == BLE_OK);
		} else {
			printk("ERROR usage ONE <n 0..%u> <s 0..10>\r\n", ble_sample_count() - 1u);
		}
	} else if (strcmp(cmd, "SESSION") == 0) {
		/* Dry run of the plan's cycles over the current link (no self-test, no idle windows). */
		a = CONFIG_WEEK10_CYCLE_GAP_MS;
		b = 0;
		c = ble_plan_cycles();
		if (argc <= 4 && (argc < 2 || parse_u32(argv[1], &a)) && (argc < 3 || parse_u32(argv[2], &b)) &&
		    (argc < 4 || parse_u32(argv[3], &c)) && a <= 10000u && b < ble_plan_cycles() &&
		    c >= 1u && c <= ble_plan_cycles() - b) {
			if (!plan_ok()) {
				printk("ERROR plan bytes differ from plan_sha256\r\n");
				return;
			}
			if (plan_needs_link(b, c) && !link_ready()) {
				printk("ERROR link not ready (start the edge peer)\r\n");
				return;
			}
			printk("SESSION BEGIN first=%u count=%u gap_ms=%u plan_sha256=%s\r\n", b, c, a,
			       ble_plan_sha256());
			const unsigned ok = run_plan(b, c, a, true);
			print_link();
			print_stacks();
			printk("SESSION END first=%u count=%u ok=%u failed=%u\r\n", b, c, ok, c - ok);
		} else {
			printk("ERROR usage SESSION [gap_ms 0..10000] [first] [count]\r\n");
		}
	} else {
		printk("ERROR unknown command (HELP)\r\n");
	}
}
#endif /* WEEK10_CONSOLE */

/* ------------------------------------------------------------------ main */

int main(void)
{
	if (markers_init() != 0 || marker_ctrl_init() != 0) {
		return -1;
	}
	leds_off();
	dwt_init();
	__asm__ volatile("" : : "r"(build_id) : "memory");

#if defined(CONFIG_WEEK10_BLE)
	k_msleep(100);
	if (!plan_ok()) {
		/* Plan bytes differ from WEEK10_BLE_PLAN_SHA256: no session. Ten 5 ms CTRL pulses mark it. */
		for (unsigned i = 0; i < 10u; ++i) {
			marker_ctrl_on();
			k_msleep(5);
			marker_ctrl_off();
			k_msleep(45);
		}
		k_sleep(K_FOREVER);
	}
	markers_selftest();
	k_sleep(K_SECONDS(CONFIG_WEEK10_BOOT_IDLE_S));   /* W7-D3: idle window, radio off */
	if (link_init() != 0) {
		k_sleep(K_FOREVER);
	}
	ble_cycle_init();   /* after link_init(): it resets the reassembler's stream mask */
	session_after_idle(false);
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
	ble_cycle_init();   /* after link_init(): it resets the reassembler's stream mask */
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
