/*
 * Week 9 Device firmware, E_dev(s) for every s (decisions W9-D1..D7, criteria TC1-TC8 in
 * CLAUDE.local.md until the week 9 report). Fork of week8/main.c (hash-locked) without the radio,
 * the NVS nonce store and I2: the cycle is dev_cycle.c (CTRL -> HEAD) at the split of the W9-D4
 * plan (week9_plan.h, 50 rounds x 11 splits, round k = W8-D3 sample k).
 *
 * dev-usb  USB CDC, no radio: VERIFY ALL (550 q/scale SHA-256, TC2), TDEV (DWT t_dev of every s,
 *          IRQs locked, TC2), ONE <n> <s>, SESSION [gap_ms] (dry run of the plan, every cycle
 *          printed), MARKERS. Powered by the laptop: its timings are debug evidence only.
 * dev      no USB/console/LED, no bt_enable, no NVS: at power-on runs the PPK2 session by itself:
 *          plan self-check -> self-test D0..D4 -> idle 30 s -> 550 cycles, 1 s apart -> sleep.
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

#include "dev_cycle.h"
#include "marker_ctrl.h"
#include "markers.h"
#include "sha256.h"
#include "week9_build.h"

#if defined(CONFIG_BT)
#error "Week 9 E_dev images have no radio (W9-D1)"
#endif

#if defined(CONFIG_WEEK9_DEV_USB)
#define WEEK9_CONSOLE 1
#include <zephyr/drivers/uart.h>
#include <zephyr/sys/reboot.h>
BUILD_ASSERT(DT_NODE_HAS_COMPAT(DT_CHOSEN(zephyr_console), zephyr_cdc_acm_uart),
	     "dev-usb uses USB CDC ACM as control/debug console");
static const struct device *const console_device = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));
#else
#define WEEK9_CONSOLE 0
BUILD_ASSERT(!IS_ENABLED(CONFIG_PRINTK) && !IS_ENABLED(CONFIG_USB_DEVICE_STACK_NEXT) &&
	     !IS_ENABLED(CONFIG_SERIAL), "dev image: no USB, console or printk (TC1)");
#endif

#define KERNEL_NAME "FAST"
#define CPU_HZ 64000000u

/* Kept in every image (check_week9_build.py: build_id_in_image), also without a console. */
static const char build_id[] = "WEEK9_BUILD_ID=" WEEK9_BUILD_ID;

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
		k_msleep(CONFIG_WEEK9_SELFTEST_MS);
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
	dev_plan_digest(hex);
	return strcmp(hex, dev_plan_sha256()) == 0;
}

/* ------------------------------------------------------------------ console (dev-usb) */

#if WEEK9_CONSOLE
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

static void print_cycle(unsigned i, const struct dev_result *r)
{
	printk("CYCLE i=%u round=%u n=%u id=%s s=%u bytes=%u ctrl_cyc=%u head_cyc=%u quant_cyc=%u "
	       "head_us=%u res=%s\r\n",
	       i, dev_plan_sample(i), r->sample, dev_sample_id(r->sample), r->split, r->bytes_payload,
	       r->ctrl_cycles, r->head_cycles, r->quant_cycles, r->head_cycles / (CPU_HZ / 1000000u),
	       dev_error_names[r->error]);
}
#endif /* WEEK9_CONSOLE */

/* ------------------------------------------------------------------ session */

/* Cycles first .. first + count - 1 of the W9-D4 plan, gap_ms apart (the energy session: all 550). */
static unsigned run_plan(unsigned first, unsigned count, uint32_t gap_ms, bool verbose)
{
	unsigned ok = 0;
	for (unsigned i = first; i < first + count && i < dev_plan_cycles(); ++i) {
		struct dev_result r;
		dev_cycle_run(dev_plan_split(i), dev_plan_sample(i), &r);
		ok += r.error == DEV_OK;
#if WEEK9_CONSOLE
		if (verbose) {
			print_cycle(i, &r);
		}
#else
		ARG_UNUSED(verbose);
#endif
		k_msleep(gap_ms);
	}
	return ok;
}

#if WEEK9_CONSOLE
static void hex_digest(const void *data, size_t length, char out[65])
{
	uint8_t digest[32];
	sha256(data, length, digest);
	sha256_hex(digest, out);
}

/* TC2: q/scale of the 50 samples at one or every split vs the host reference (refs.csv). */
static void verify_split(unsigned split)
{
	for (unsigned n = 0; n < dev_sample_count(); ++n) {
		struct dev_tensor t;
		char q_hex[65], s_hex[65];
		if (dev_head(split, n, &t, NULL) != 0) {
			printk("VQ n=%u s=%u ERROR\r\n", n, split);
			continue;
		}
		hex_digest(t.q, (size_t)t.channels * t.length, q_hex);
		hex_digest(t.scale_le, 2u * t.channels, s_hex);
		printk("VQ n=%u id=%s s=%u C=%u L=%u bytes=%u q_sha256=%s scale_sha256=%s\r\n", n,
		       dev_sample_id(n), split, t.channels, t.length,
		       (unsigned)(t.channels * t.length + 2u * t.channels), q_hex, s_hex);
		pace();
	}
}

/* TC2: DWT t_dev of every split, week 7 BENCH method (20 warm-up runs on sample 0, IRQs locked
 * for each run, markers and printing outside), measured over the 50 samples, one run each.
 * head = head_fast_run only (week 7 BENCH FAST), total = head + quantization (the D0 phase). */
#define TDEV_WARMUP 20u

static void tdev_split(unsigned split)
{
	uint64_t sum_head = 0, sum_quant = 0, sum_total = 0;
	uint32_t head_lo = UINT32_MAX, head_hi = 0, total_lo = UINT32_MAX, total_hi = 0;
	const unsigned runs = dev_sample_count();
	for (unsigned i = 0; i < TDEV_WARMUP + runs; ++i) {
		const unsigned n = i < TDEV_WARMUP ? 0u : i - TDEV_WARMUP;
		struct dev_tensor t;
		uint32_t head = 0;
		const unsigned key = irq_lock();
		const uint32_t start = dev_cycle_now();
		const int status = dev_head(split, n, &t, &head);
		const uint32_t end = dev_cycle_now();
		irq_unlock(key);
		if (status != 0) {
			printk("TD s=%u n=%u ERROR\r\n", split, n);
			return;
		}
		if (i < TDEV_WARMUP) {
			continue;
		}
		const uint32_t quant = dev_last_quant_cycles();
		const uint32_t total = end - start;
		printk("TD s=%u n=%u head_cyc=%u quant_cyc=%u total_cyc=%u\r\n", split, n, head, quant,
		       total);
		sum_head += head;
		sum_quant += quant;
		sum_total += total;
		head_lo = MIN(head_lo, head);
		head_hi = MAX(head_hi, head);
		total_lo = MIN(total_lo, total);
		total_hi = MAX(total_hi, total);
		if (n % 16u == 15u) {
			pace();
		}
	}
	printk("TDSUM s=%u runs=%u warmup=%u irq=locked cpu_hz=%u head_min=%u head_max=%u "
	       "head_mean_x100=%llu quant_mean_x100=%llu total_min=%u total_max=%u total_mean_x100=%llu\r\n",
	       split, runs, TDEV_WARMUP, SystemCoreClock, head_lo, head_hi,
	       (unsigned long long)(sum_head * 100u / runs), (unsigned long long)(sum_quant * 100u / runs),
	       total_lo, total_hi, (unsigned long long)(sum_total * 100u / runs));
	pace();
}

/* ------------------------------------------------------------------ banner / dispatch */

static void print_banner(void)
{
	char hex[65];
	dev_plan_digest(hex);
	printk("READY WEEK9 build=%s variant=%s kernel=%s rounds=%u splits=%u cycles=%u samples=%u "
	       "gap_ms=%u boot_idle_s=%u ctrl_min_us=%u selftest_ms=%u d4_pin=P0.%u set_sha256=%s "
	       "plan_sha256=%s plan_device_sha256=%s plan_ok=%u\r\n",
	       WEEK9_BUILD_ID, WEEK9_VARIANT, KERNEL_NAME, dev_sample_count(), DEV_SPLITS,
	       dev_plan_cycles(), dev_sample_count(), CONFIG_WEEK9_CYCLE_GAP_MS,
	       CONFIG_WEEK9_BOOT_IDLE_S, CONFIG_WEEK9_CTRL_MIN_US, CONFIG_WEEK9_SELFTEST_MS,
	       MARKER_CTRL_PIN, dev_set_sha256(), dev_plan_sha256(), hex,
	       strcmp(hex, dev_plan_sha256()) == 0);
}

static void print_help(void)
{
	printk("COMMANDS HELP | STATUS | STACK | MARKERS | REBOOT\r\n");
	printk("COMMANDS VERIFY ALL | VERIFY <s> | TDEV ALL | TDEV <s> | ONE <n> <s> | "
	       "SESSION [gap_ms] [first] [count]\r\n");
}

static bool parse_split(const char *text, uint32_t *split)
{
	return parse_u32(text, split) && *split < DEV_SPLITS;
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
		printk("MARKERS END order=D0,D1,D2,D3,D4 width_ms=%u\r\n", CONFIG_WEEK9_SELFTEST_MS);
	} else if (strcmp(cmd, "REBOOT") == 0) {
		printk("REBOOT\r\n");
		k_msleep(100);
		sys_reboot(SYS_REBOOT_COLD);
	} else if (strcmp(cmd, "VERIFY") == 0 && argc == 2 &&
		   (strcmp(argv[1], "ALL") == 0 || parse_split(argv[1], &a))) {
		const bool all = strcmp(argv[1], "ALL") == 0;
		for (unsigned s = all ? 0u : a; s < (all ? DEV_SPLITS : a + 1u); ++s) {
			verify_split(s);
		}
		printk("VERIFY END kernel=%s samples=%u splits=%s set_sha256=%s\r\n", KERNEL_NAME,
		       dev_sample_count(), all ? "ALL" : argv[1], dev_set_sha256());
	} else if (strcmp(cmd, "TDEV") == 0 && argc == 2 &&
		   (strcmp(argv[1], "ALL") == 0 || parse_split(argv[1], &a))) {
		const bool all = strcmp(argv[1], "ALL") == 0;
		for (unsigned s = all ? 0u : a; s < (all ? DEV_SPLITS : a + 1u); ++s) {
			tdev_split(s);
		}
		printk("TDEV END kernel=%s splits=%s\r\n", KERNEL_NAME, all ? "ALL" : argv[1]);
	} else if (strcmp(cmd, "ONE") == 0) {
		/* One cycle (CTRL + HEAD with markers) of sample n at split s. */
		if (argc == 3 && parse_u32(argv[1], &a) && a < dev_sample_count() &&
		    parse_split(argv[2], &b)) {
			struct dev_result r;
			printk("ONE BEGIN n=%u s=%u\r\n", a, b);
			dev_cycle_run(b, a, &r);
			print_cycle(0, &r);
			printk("ONE END ok=%u\r\n", r.error == DEV_OK);
		} else {
			printk("ERROR usage ONE <n 0..%u> <s 0..10>\r\n", dev_sample_count() - 1u);
		}
	} else if (strcmp(cmd, "SESSION") == 0) {
		/* Dry run of the dev session's cycles (no self-test, no idle window). */
		a = CONFIG_WEEK9_CYCLE_GAP_MS;
		b = 0;
		c = dev_plan_cycles();
		if (argc <= 4 && (argc < 2 || parse_u32(argv[1], &a)) && (argc < 3 || parse_u32(argv[2], &b)) &&
		    (argc < 4 || parse_u32(argv[3], &c)) && a <= 10000u && b < dev_plan_cycles() &&
		    c >= 1u && c <= dev_plan_cycles() - b) {
			printk("SESSION BEGIN first=%u count=%u gap_ms=%u plan_sha256=%s\r\n", b, c, a,
			       dev_plan_sha256());
			const unsigned ok = run_plan(b, c, a, true);
			print_stacks();
			printk("SESSION END first=%u count=%u ok=%u failed=%u\r\n", b, c, ok, c - ok);
		} else {
			printk("ERROR usage SESSION [gap_ms 0..10000] [first] [count]\r\n");
		}
	} else {
		printk("ERROR unknown command (HELP)\r\n");
	}
}
#endif /* WEEK9_CONSOLE */

/* ------------------------------------------------------------------ main */

int main(void)
{
	if (markers_init() != 0 || marker_ctrl_init() != 0) {
		return -1;
	}
	leds_off();
	dwt_init();
	__asm__ volatile("" : : "r"(build_id) : "memory");
	dev_cycle_init();

#if defined(CONFIG_WEEK9_DEV)
	k_msleep(100);
	if (!plan_ok()) {
		/* Plan bytes differ from WEEK9_PLAN_SHA256: no session. Ten 5 ms CTRL pulses mark it. */
		for (unsigned i = 0; i < 10u; ++i) {
			marker_ctrl_on();
			k_msleep(5);
			marker_ctrl_off();
			k_msleep(45);
		}
		k_sleep(K_FOREVER);
	}
	markers_selftest();
	k_sleep(K_SECONDS(CONFIG_WEEK9_BOOT_IDLE_S));   /* W7-D3: idle window, radio off */
	(void)run_plan(0, dev_plan_cycles(), CONFIG_WEEK9_CYCLE_GAP_MS, false);
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
	bool connected_before = false;
	for (;;) {
		uint32_t dtr = 0;
		const bool connected =
			uart_line_ctrl_get(console_device, UART_LINE_CTRL_DTR, &dtr) == 0 && dtr;
		if (connected && !connected_before) {
			k_msleep(100);
			print_banner();
			printk("BOOT plan_ok=%u\r\n", plan_ok());
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
