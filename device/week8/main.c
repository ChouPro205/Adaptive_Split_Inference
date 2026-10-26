/*
 * Week 8 Device firmware, G2 end-to-end (decisions W8-D1..D7, criteria TC1-TC9: appendix of
 * docs/sv1_device_week8_report.md). Fork of week7/main.c (hash-locked) without the bench variant; the cycle is
 * g2_cycle.c over the 100 W8-D3 samples of week8_inputs.h at s=2, and every session is paired
 * (W8-D1): pair k sends sample k mod 100 as P1 then P0 when k is even, P0 then P1 when k is odd.
 *
 * energy-usb  USB CDC + BLE + NVS nonce: VERIFY (TC2 byte checks), ONE, PAIRS, SESSION, MARKERS.
 *             Every cycle prints the received logits (FP32 bits) and the label read on the dongle.
 *             Debug evidence only: powered by the laptop, its timings are not energy numbers.
 * energy      no USB/console/LED; at power-on runs the PPK2 session by itself (week 9 image):
 *             nonce block reserved (one D1 pulse) -> self-test D0..D4 -> idle with the radio off
 *             -> BLE, link + parameters -> connected idle -> CONFIG_WEEK8_PAIRS pairs -> stop and
 *             stay off-air (week8/ble_link.c, W8-D2).
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
#include "frag.h"
#include "g2_cycle.h"
#include "marker_ctrl.h"
#include "markers.h"
#include "nonce_nvs.h"
#include "sha256.h"
#include "week8_build.h"

#if defined(CONFIG_WEEK7_BENCH)
#error "Week 8 builds energy-usb and energy only; bench is device/week7"
#endif

#if defined(CONFIG_WEEK7_ENERGY_USB)
#define WEEK8_CONSOLE 1
#include <zephyr/drivers/uart.h>
#include <zephyr/sys/reboot.h>
BUILD_ASSERT(DT_NODE_HAS_COMPAT(DT_CHOSEN(zephyr_console), zephyr_cdc_acm_uart),
	     "USB variants use USB CDC ACM as control/debug console");
static const struct device *const console_device = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));
#else
#define WEEK8_CONSOLE 0
BUILD_ASSERT(!IS_ENABLED(CONFIG_PRINTK) && !IS_ENABLED(CONFIG_USB_DEVICE_STACK_NEXT) &&
	     !IS_ENABLED(CONFIG_SERIAL), "energy image: no USB, console or printk (TC5)");
#endif

#if defined(CONFIG_WEEK7_KERNEL_FAST)
#define KERNEL_NAME "FAST"
#else
#define KERNEL_NAME "W4"
#endif

#define CPU_HZ 64000000u

/* Kept in every image (check_week8_build.py: build_id_in_image), also without a console. */
static const char build_id[] = "WEEK8_BUILD_ID=" WEEK8_BUILD_ID;

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
		k_msleep(CONFIG_WEEK7_SELFTEST_MS);
		if (m < 4u) {
			marker_off((enum marker_id)m);
		} else {
			marker_ctrl_off();
		}
	}
}

/* ------------------------------------------------------------------ console (energy-usb) */

#if WEEK8_CONSOLE
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
#endif /* WEEK8_CONSOLE */

/* ------------------------------------------------------------------ session */

static bool session_nonce_ready;
static uint64_t session_reserved_sequence;

/* Reserve this boot's sequence block now (one NVS write, one D1 pulse) so that no cycle ever
 * writes Flash (W7-D2). The sequence used to trigger it is discarded: skipping is always safe. */
static bool nonce_prepare(void)
{
	uint8_t nonce[12];
	struct nonce_nvs_info info;
	nonce_nvs_get_info(&info);
	if (info.status != NONCE_READY) {
		return false;
	}
	return nonce_nvs_allocate(&session_reserved_sequence, nonce) == 0;
}

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

struct run_totals {
	unsigned ok;
	unsigned failed;
	unsigned label_match;
	unsigned label_mismatch;
};

#if WEEK8_CONSOLE
static void print_cycle(unsigned i, unsigned pair, const struct cycle_result *r)
{
	const uint32_t us = CPU_HZ / 1000000u;
	uint32_t bits[G2_LOGITS];
	memcpy(bits, r->logits, sizeof(bits));
	const uint8_t ref = g2_reference_label(r->sample);
	printk("CYCLE i=%u pair=%u rho=%s n=%u id=%s s=%u rid=%08x seq=%llu len=%u frags=%u mtu=%u "
	       "ctrl_us=%u head_us=%u quant_us=%u prot_us=%u enc_us=%u tx_us=%u wait_us=%u "
	       "enomem=%u invalid=%u nonce_writes=%u status=%u res=%s "
	       "logits=%08x,%08x,%08x,%08x,%08x label=%u ref=%u match=%u\r\n",
	       i, pair, r->p1 ? "P1" : "P0", r->sample, g2_sample_id(r->sample), r->split,
	       r->request_id, r->sequence, r->frame_length, r->fragments, r->att_mtu,
	       r->ctrl_cycles / us, r->head_cycles / us, r->quant_cycles / us, r->prot_cycles / us,
	       r->encode_cycles / us, r->tx_cycles / us, r->wait_cycles / us, r->enomem_retries,
	       r->invalid_responses, r->nonce_writes, r->response_status, cycle_error_names[r->error],
	       bits[0], bits[1], bits[2], bits[3], bits[4], r->label, ref,
	       r->error == CYCLE_OK && r->label == ref);
}
#endif

static void run_one(unsigned i, unsigned pair, unsigned sample, bool p1, bool verbose,
		    struct run_totals *t)
{
	struct cycle_result r;
	for (unsigned waited = 0; !link_ready() && waited < 300u; ++waited) {
		(void)k_sem_take(&link_wake, K_MSEC(100));   /* reconnect: at most 30 s */
	}
	g2_cycle_run(sample, p1, &r);
	t->ok += r.error == CYCLE_OK;
	t->failed += r.error != CYCLE_OK;
	if (r.error == CYCLE_OK) {
		const bool match = r.label == g2_reference_label(sample);
		t->label_match += match;
		t->label_mismatch += !match;
	}
#if WEEK8_CONSOLE
	if (verbose) {
		print_cycle(i, pair, &r);
	}
#else
	ARG_UNUSED(i);
	ARG_UNUSED(pair);
	ARG_UNUSED(verbose);
#endif
	k_msleep(CONFIG_WEEK7_CYCLE_GAP_MS);
}

/* Pairs first .. first + count - 1, two cycles each in the W8-D1 order. */
static void run_pairs(unsigned first, unsigned count, bool verbose)
{
	struct run_totals t = {0};
	for (unsigned k = 0; k < count; ++k) {
		const unsigned pair = first + k;
		const unsigned sample = g2_pair_sample(pair, g2_sample_count());
		for (unsigned slot = 0; slot < 2u; ++slot) {
			run_one(2u * k + slot, pair, sample, g2_slot_is_p1(pair, slot), verbose, &t);
		}
	}
#if WEEK8_CONSOLE
	printk("PAIRS END first=%u pairs=%u cycles=%u ok=%u failed=%u label_match=%u label_mismatch=%u\r\n",
	       first, count, 2u * count, t.ok, t.failed, t.label_match, t.label_mismatch);
#endif
}

/* The part of the energy session after the radio idle window (link_init already called). */
static void session_after_idle(bool verbose)
{
	wait_link_ready();
	if (CONFIG_WEEK7_CONN_INTERVAL_1250US > 0) {
		/* W7-D7: latency 0, supervision timeout 4 s; the central decides (EVT CONN_PARAM). */
		(void)link_request_conn_params(CONFIG_WEEK7_CONN_INTERVAL_1250US,
					       CONFIG_WEEK7_CONN_INTERVAL_1250US, 0, 400);
	}
	k_sleep(K_SECONDS(CONFIG_WEEK7_SETTLE_S));
#if WEEK8_CONSOLE
	if (verbose) {
		struct link_info li;
		link_get_info(&li);
		printk("SESSION link att_mtu=%u interval_1250us=%u latency=%u phy_tx=%u\r\n",
		       li.att_mtu, li.interval_1250us, li.latency, li.tx_phy);
	}
#endif
	k_sleep(K_SECONDS(CONFIG_WEEK7_CONNECTED_IDLE_S));
	run_pairs(0, CONFIG_WEEK8_PAIRS, verbose);
	(void)link_disconnect();
}

#if WEEK8_CONSOLE
static void hex_digest(const void *data, size_t length, char out[65])
{
	uint8_t digest[32];
	sha256(data, length, digest);
	sha256_hex(digest, out);
}

static const char *nonce_status_name(enum nonce_status status)
{
	return status == NONCE_READY ? "READY" : status == NONCE_UNPROVISIONED ? "UNPROVISIONED" : "FAULT";
}

static void print_nonce(void)
{
	struct nonce_nvs_info ni;
	nonce_nvs_get_info(&ni);
	printk("NONCE status=%s reason=%s reserved_through=%llu next=%llu limit=%llu key_id=%u "
	       "sender_id=%u key_check=%02x%02x%02x%02x%02x%02x%02x%02x writes=%u "
	       "session_reserved_sequence=%llu\r\n",
	       nonce_status_name(ni.status), nonce_reason_names[ni.reason], ni.persisted, ni.next,
	       ni.limit, ni.key_id, ni.sender_id, ni.kcv[0], ni.kcv[1], ni.kcv[2], ni.kcv[3],
	       ni.kcv[4], ni.kcv[5], ni.kcv[6], ni.kcv[7], ni.writes, session_reserved_sequence);
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

/* TC2: q/scale of the 100 samples vs the host reference (samples.csv), requests vs the Python
 * reference. P1 uses the PUBLIC_TEST_ONLY key 00..1f with sequence n+1 (never the bench key). */
static void command_verify(void)
{
	static uint8_t frame[FRAG_MAX_FRAME];
	uint8_t public_key[32], nonce[12];
	const unsigned split = CONFIG_WEEK7_SPLIT;
	for (unsigned i = 0; i < sizeof(public_key); ++i) {
		public_key[i] = (uint8_t)i;
	}
	for (unsigned n = 0; n < g2_sample_count(); ++n) {
		struct pipeline_tensor t;
		char q_hex[65], s_hex[65], r_hex[65];
		if (pipeline_head(split, n, &t) != 0) {
			printk("VQ n=%u s=%u ERROR\r\n", n, split);
			continue;
		}
		hex_digest(t.q, (size_t)t.channels * t.length, q_hex);
		hex_digest(t.scale_le, 2u * t.channels, s_hex);
		printk("VQ n=%u id=%s s=%u C=%u L=%u q_sha256=%s scale_sha256=%s\r\n", n, g2_sample_id(n),
		       split, t.channels, t.length, q_hex, s_hex);
		pace();
		uint32_t prot = 0;
		size_t len = pipeline_request(&t, n + 1u, NULL, NULL, frame, &prot);
		hex_digest(frame, len, r_hex);
		printk("VREQ n=%u s=%u rho=P0 rid=%u len=%u sha256=%s\r\n", n, split, n + 1u,
		       (unsigned)len, r_hex);
		pace();
		const uint32_t sender = PKT_SENDER_ID;
		const uint64_t sequence = n + 1u;
		for (unsigned i = 0; i < 4u; ++i) {
			nonce[i] = (uint8_t)(sender >> (8u * i));
		}
		for (unsigned i = 0; i < 8u; ++i) {
			nonce[4u + i] = (uint8_t)(sequence >> (8u * i));
		}
		len = pipeline_request(&t, n + 1u, public_key, nonce, frame, &prot);
		hex_digest(frame, len, r_hex);
		printk("VREQ n=%u s=%u rho=P1 rid=%u seq=%u len=%u sha256=%s prot_us=%u\r\n", n, split,
		       n + 1u, n + 1u, (unsigned)len, r_hex, prot / (CPU_HZ / 1000000u));
		pace();
	}
	printk("VERIFY END kernel=%s samples=%u set_sha256=%s\r\n", KERNEL_NAME, g2_sample_count(),
	       g2_set_sha256());
}

/* ------------------------------------------------------------------ banner / dispatch */

static void print_banner(void)
{
	printk("READY WEEK8 build=%s variant=%s kernel=%s split=%u samples=%u pairs=%u gap_ms=%u "
	       "boot_idle_s=%u connected_idle_s=%u ctrl_min_us=%u timeout_ms=%u conn_interval_1250us=%u "
	       "d4_pin=P0.%u set_sha256=%s\r\n",
	       WEEK8_BUILD_ID, WEEK8_VARIANT, KERNEL_NAME, CONFIG_WEEK7_SPLIT, g2_sample_count(),
	       CONFIG_WEEK8_PAIRS, CONFIG_WEEK7_CYCLE_GAP_MS, CONFIG_WEEK7_BOOT_IDLE_S,
	       CONFIG_WEEK7_CONNECTED_IDLE_S, CONFIG_WEEK7_CTRL_MIN_US,
	       CONFIG_WEEK7_RESPONSE_TIMEOUT_MS, CONFIG_WEEK7_CONN_INTERVAL_1250US, MARKER_CTRL_PIN,
	       g2_set_sha256());
	print_nonce();
	print_link();
}

static void print_help(void)
{
	printk("COMMANDS HELP | STATUS | STACK | MARKERS | REBOOT\r\n");
	printk("COMMANDS NONCE | CONNPARAM <min> <max> | VERIFY | ONE <n> P1|P0 | PAIRS <first> <count> "
	       "| SESSION\r\n");
}

/* P1 refused without a READY nonce; at most one reservation block of P1 cycles per command. */
static bool cycles_allowed(unsigned p1_cycles)
{
	if (!link_ready()) {
		printk("ERROR link not ready (start the edge peer)\r\n");
		return false;
	}
	if (p1_cycles > 0u && !session_nonce_ready) {
		printk("ERROR nonce not READY: P1 refused\r\n");
		return false;
	}
	return true;
}

static void dispatch(void)
{
	char *argv[MAX_ARGS];
	const int argc = split_args(line, argv);
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
		printk("MARKERS END order=D0,D1,D2,D3,D4 width_ms=%u\r\n", CONFIG_WEEK7_SELFTEST_MS);
	} else if (strcmp(cmd, "REBOOT") == 0) {
		printk("REBOOT\r\n");
		k_msleep(100);
		sys_reboot(SYS_REBOOT_COLD);
	} else if (strcmp(cmd, "NONCE") == 0) {
		print_nonce();
	} else if (strcmp(cmd, "CONNPARAM") == 0 && argc == 3) {
		uint32_t lo = 0, hi = 0;
		if (parse_u32(argv[1], &lo) && parse_u32(argv[2], &hi) && lo >= 6u && lo <= hi &&
		    hi <= 3200u) {
			printk("CONNPARAM request min_1250us=%u max_1250us=%u err=%d\r\n", lo, hi,
			       link_request_conn_params((uint16_t)lo, (uint16_t)hi, 0, 400));
		} else {
			printk("ERROR usage CONNPARAM <min> <max> (units of 1.25 ms, 6..3200)\r\n");
		}
	} else if (strcmp(cmd, "VERIFY") == 0 && argc == 1) {
		command_verify();
	} else if (strcmp(cmd, "ONE") == 0) {
		/* One cycle of one sample: the first end-to-end tensor with a new peer (B4). */
		uint32_t n = 0;
		const bool p1 = argc == 3 && strcmp(argv[2], "P1") == 0;
		if (argc == 3 && parse_u32(argv[1], &n) && n < g2_sample_count() &&
		    (p1 || strcmp(argv[2], "P0") == 0)) {
			if (cycles_allowed(p1 ? 1u : 0u)) {
				struct run_totals t = {0};
				printk("ONE BEGIN n=%u rho=%s\r\n", n, p1 ? "P1" : "P0");
				run_one(0, 0, n, p1, true, &t);
				printk("ONE END ok=%u label_match=%u\r\n", t.ok, t.label_match);
			}
		} else {
			printk("ERROR usage ONE <n 0..%u> P1|P0\r\n", g2_sample_count() - 1u);
		}
	} else if (strcmp(cmd, "PAIRS") == 0) {
		/* Same order as the energy session (W8-D1), starting at pair <first>. */
		uint32_t first = 0, count = 0;
		if (argc == 3 && parse_u32(argv[1], &first) && parse_u32(argv[2], &count) &&
		    count > 0u && count < NONCE_RESERVE_BLOCK && first < 100000u) {
			if (cycles_allowed(count)) {
				printk("PAIRS BEGIN first=%u pairs=%u\r\n", first, count);
				run_pairs(first, count, true);
				print_nonce();
				print_stacks();
			}
		} else {
			printk("ERROR usage PAIRS <first> <count 1..%u>\r\n", NONCE_RESERVE_BLOCK - 1u);
		}
	} else if (strcmp(cmd, "SESSION") == 0) {
		if (!session_nonce_ready) {
			printk("ERROR nonce not READY: the paired session needs P1\r\n");
			return;
		}
		printk("SESSION BEGIN pairs=%u\r\n", CONFIG_WEEK8_PAIRS);
		session_after_idle(true);
		print_nonce();
		print_stacks();
		printk("SESSION END\r\n");
	} else {
		printk("ERROR unknown command (HELP)\r\n");
	}
}
#endif /* WEEK8_CONSOLE */

/* ------------------------------------------------------------------ main */

int main(void)
{
	if (markers_init() != 0 || marker_ctrl_init() != 0) {
		return -1;
	}
	leds_off();
	dwt_init();
	__asm__ volatile("" : : "r"(build_id) : "memory");
	nonce_nvs_init();
	session_nonce_ready = nonce_prepare();

#if defined(CONFIG_WEEK7_ENERGY)
	k_msleep(100);
	if (!session_nonce_ready) {
		/* No nonce: never send I2/1. Ten 5 ms CTRL pulses mark the refusal on the trace. */
		for (unsigned i = 0; i < 10u; ++i) {
			marker_ctrl_on();
			k_msleep(5);
			marker_ctrl_off();
			k_msleep(45);
		}
		k_sleep(K_FOREVER);
	}
	markers_selftest();
	k_sleep(K_SECONDS(CONFIG_WEEK7_BOOT_IDLE_S));   /* W7-D3: idle window, radio off */
	if (link_init() != 0) {
		k_sleep(K_FOREVER);
	}
	g2_cycle_init();   /* after link_init(): it resets the reassembler's stream mask */
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
	g2_cycle_init();   /* after link_init(): it resets the reassembler's stream mask */
	bool connected_before = false;
	for (;;) {
		uint32_t dtr = 0;
		const bool connected =
			uart_line_ctrl_get(console_device, UART_LINE_CTRL_DTR, &dtr) == 0 && dtr;
		if (connected && !connected_before) {
			k_msleep(100);
			print_banner();
			printk("BOOT bt_enable=%d nonce_session_ready=%u\r\n", bt_err, session_nonce_ready);
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
