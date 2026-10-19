/*
 * Week 7 Device firmware (plan: CLAUDE.local.md "Kế hoạch tuần hiện tại"; criteria TC1-TC9).
 *
 * bench       USB CDC; both FP32 kernels: CMP ALL (220 cases bitwise), CMP MIX (16 interleaved),
 *             BENCH <W4|FAST|ALL> [s] (week 4 method: 20 warm-up + 100 runs, IRQs locked,
 *             sample 0, DWT). No radio. (TC7)
 * energy-usb  USB CDC + BLE + NVS nonce: VERIFY (TC4 byte checks), CYCLES, SESSION, MARKERS.
 *             Debug evidence only: powered by the laptop, its timings are not energy numbers.
 * energy      no USB/console/LED; at power-on runs the PPK2 session by itself (TC1, TC5, TC6):
 *             nonce block reserved (one D1 pulse) -> self-test D0..D4 -> idle with the radio off
 *             -> BLE, link + parameters -> connected idle -> P1 cycles, then P0 cycles -> stop.
 */
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include <cmsis_core.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/irq.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/util.h>

#include "head_fast.h"
#include "marker_ctrl.h"
#include "markers.h"
#include "sha256.h"
#include "week7_build.h"

#if defined(CONFIG_WEEK7_BENCH)
#include "week4_inputs.h"
#else
#include "ble_link.h"
#include "energy_cycle.h"
#include "frag.h"
#include "nonce_nvs.h"
#endif

#if defined(CONFIG_WEEK7_BENCH) || defined(CONFIG_WEEK7_ENERGY_USB)
#define WEEK7_CONSOLE 1
#include <zephyr/drivers/uart.h>
#include <zephyr/sys/reboot.h>
BUILD_ASSERT(DT_NODE_HAS_COMPAT(DT_CHOSEN(zephyr_console), zephyr_cdc_acm_uart),
	     "USB variants use USB CDC ACM as control/debug console");
static const struct device *const console_device = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));
#else
#define WEEK7_CONSOLE 0
BUILD_ASSERT(!IS_ENABLED(CONFIG_PRINTK) && !IS_ENABLED(CONFIG_USB_DEVICE_STACK_NEXT) &&
	     !IS_ENABLED(CONFIG_SERIAL), "energy image: no USB, console or printk (TC5)");
#endif

#if defined(CONFIG_WEEK7_KERNEL_FAST)
#define KERNEL_NAME "FAST"
#else
#define KERNEL_NAME "W4"
#endif

#define CPU_HZ 64000000u

/* Kept in every image (check_week7_build.py: build_id_in_image), also without a console. */
static const char build_id[] = "WEEK7_BUILD_ID=" WEEK7_BUILD_ID;

static void dwt_init(void)
{
	CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
	DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

static inline uint32_t dwt_now(void)
{
	__asm__ volatile("" ::: "memory");
	const uint32_t cycles = DWT->CYCCNT;
	__asm__ volatile("" ::: "memory");
	return cycles;
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

/* TC1: D0 HEAD, D1 PROT, D2 TX, D3 WAIT, D4 CTRL, one after another, back to back. */
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

/* ------------------------------------------------------------------ console (USB variants) */

#if WEEK7_CONSOLE
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
#endif /* WEEK7_CONSOLE */

/* ------------------------------------------------------------------ bench (TC7) */

#if defined(CONFIG_WEEK7_BENCH)
#define WARMUP_COUNT 20U
#define MEASURE_COUNT 100U
#define CASES (WEEK4_SAMPLE_COUNT * WEEK4_SPLIT_COUNT)

static float reference[WEEK4_BUFFER_COUNT];
static uint8_t reference_hash[CASES][32];
static bool reference_valid[CASES];
static uint32_t measured_cycles[MEASURE_COUNT];

/* Same 16 (sample, split) pairs as test_week7_host.py MIXED; kernel alternates W4/FAST. */
static const uint8_t mixed[16][2] = {
	{3, 10}, {0, 0}, {19, 5}, {7, 2}, {12, 8}, {5, 1}, {19, 10}, {0, 3},
	{8, 6}, {14, 4}, {2, 9}, {11, 7}, {17, 2}, {6, 10}, {9, 0}, {1, 5},
};

static int run_kernel(bool fast, unsigned sample, unsigned split, struct week4_result *result)
{
	return fast ? head_fast_run(split, week4_inputs[sample], result)
		    : week4_run_head(split, week4_inputs[sample], result);
}

static void cmp_all(void)
{
	unsigned pass = 0;
	for (unsigned sample = 0; sample < WEEK4_SAMPLE_COUNT; ++sample) {
		for (unsigned split = 0; split < WEEK4_SPLIT_COUNT; ++split) {
			struct week4_result result;
			const unsigned index = sample * WEEK4_SPLIT_COUNT + split;
			int status = run_kernel(false, sample, split, &result);
			const unsigned count = result.shape.count;
			if (status == 0) {
				memcpy(reference, result.values, count * sizeof(float));
				status = run_kernel(true, sample, split, &result);
			}
			const bool equal = status == 0 && result.shape.count == count &&
					   memcmp(reference, result.values, count * sizeof(float)) == 0;
			char hex[65];
			sha256((const uint8_t *)reference, count * sizeof(float), reference_hash[index]);
			sha256_hex(reference_hash[index], hex);
			reference_valid[index] = status == 0;
			printk("CMP n=%u s=%u count=%u w4_sha256=%s equal=%u\r\n", sample, split, count,
			       hex, equal);
			pace();
			pass += equal;
		}
	}
	printk("CMP END pass=%u total=%u\r\n", pass, CASES);
}

static void cmp_mix(void)
{
	unsigned pass = 0, known = 0;
	for (unsigned i = 0; i < ARRAY_SIZE(mixed); ++i) {
		const unsigned sample = mixed[i][0], split = mixed[i][1];
		const bool fast = (i % 2u) == 1u;
		struct week4_result result;
		const int status = run_kernel(fast, sample, split, &result);
		uint8_t digest[32];
		char hex[65];
		sha256((const uint8_t *)result.values, result.shape.count * sizeof(float), digest);
		sha256_hex(digest, hex);
		const unsigned index = sample * WEEK4_SPLIT_COUNT + split;
		int equal = -1;
		if (reference_valid[index]) {
			equal = status == 0 && memcmp(digest, reference_hash[index], 32) == 0;
			known++;
			pass += equal == 1;
		}
		printk("MIX i=%u n=%u s=%u kernel=%s sha256=%s equal_ref=%d\r\n", i, sample, split,
		       fast ? "FAST" : "W4", hex, equal);
		pace();
	}
	printk("MIX END pass=%u compared=%u total=%u\r\n", pass, known, (unsigned)ARRAY_SIZE(mixed));
}

static void bench(bool fast, unsigned split)
{
	const unsigned sample = 0;
	struct week4_result result;
	for (unsigned i = 0; i < WARMUP_COUNT + MEASURE_COUNT; ++i) {
		/* Week 4 method: markers and printing outside, IRQs locked for one head run. */
		marker_on(MARKER_HEAD);
		const unsigned key = irq_lock();
		const uint32_t start = dwt_now();
		const int status = run_kernel(fast, sample, split, &result);
		const uint32_t end = dwt_now();
		irq_unlock(key);
		marker_off(MARKER_HEAD);
		if (status != 0) {
			printk("ERROR head\r\n");
			return;
		}
		if (i >= WARMUP_COUNT) {
			measured_cycles[i - WARMUP_COUNT] = end - start;
		}
	}
	uint64_t total = 0;
	uint32_t lo = UINT32_MAX, hi = 0;
	printk("TIMING kernel=%s n=%u s=%u warmup=%u measured=%u cpu_hz=%u irq=locked\r\n",
	       fast ? "FAST" : "W4", sample, split, WARMUP_COUNT, MEASURE_COUNT, SystemCoreClock);
	for (unsigned i = 0; i < MEASURE_COUNT; ++i) {
		total += measured_cycles[i];
		lo = MIN(lo, measured_cycles[i]);
		hi = MAX(hi, measured_cycles[i]);
		printk("CYCLES kernel=%s s=%u i=%u cycles=%u\r\n", fast ? "FAST" : "W4", split, i,
		       measured_cycles[i]);
		if (i % 16U == 15U) {
			pace();
		}
	}
	printk("BENCHSUM kernel=%s s=%u min=%u max=%u mean_x100=%llu\r\n", fast ? "FAST" : "W4",
	       split, lo, hi, (unsigned long long)(total * 100u / MEASURE_COUNT));
}

static void command_bench(int argc, char **argv)
{
	uint32_t split = 0;
	if (argc == 2 && strcmp(argv[1], "ALL") == 0) {
		for (unsigned s = 0; s < WEEK4_SPLIT_COUNT; ++s) {
			bench(false, s);
			bench(true, s);
		}
		printk("BENCH END\r\n");
		return;
	}
	if (argc != 3 || (strcmp(argv[1], "W4") != 0 && strcmp(argv[1], "FAST") != 0) ||
	    !parse_u32(argv[2], &split) || split >= WEEK4_SPLIT_COUNT) {
		printk("ERROR usage BENCH W4|FAST <s> | BENCH ALL\r\n");
		return;
	}
	bench(strcmp(argv[1], "FAST") == 0, split);
	printk("BENCH END\r\n");
}
#endif /* CONFIG_WEEK7_BENCH */

/* ------------------------------------------------------------------ radio variants */

#if !defined(CONFIG_WEEK7_BENCH)
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

#if WEEK7_CONSOLE
static void print_cycle(unsigned i, const struct cycle_result *r)
{
	const uint32_t us = CPU_HZ / 1000000u;
	printk("CYCLE i=%u rho=%s n=%u s=%u rid=%08x seq=%llu len=%u frags=%u mtu=%u "
	       "ctrl_us=%u head_us=%u quant_us=%u prot_us=%u enc_us=%u tx_us=%u wait_us=%u "
	       "enomem=%u invalid=%u nonce_writes=%u status=%u res=%s\r\n",
	       i, r->p1 ? "P1" : "P0", r->sample, r->split, r->request_id, r->sequence,
	       r->frame_length, r->fragments, r->att_mtu, r->ctrl_cycles / us, r->head_cycles / us,
	       r->quant_cycles / us, r->prot_cycles / us, r->encode_cycles / us, r->tx_cycles / us,
	       r->wait_cycles / us, r->enomem_retries, r->invalid_responses, r->nonce_writes,
	       r->response_status, cycle_error_names[r->error]);
}
#endif

static void run_cycles(unsigned p1_count, unsigned p0_count, bool verbose)
{
	unsigned ok = 0, failed = 0;
	for (unsigned i = 0; i < p1_count + p0_count; ++i) {
		struct cycle_result r;
		for (unsigned waited = 0; !link_ready() && waited < 300u; ++waited) {
			(void)k_sem_take(&link_wake, K_MSEC(100));   /* reconnect: at most 30 s */
		}
		energy_cycle_run(i, i < p1_count, &r);
		ok += r.error == CYCLE_OK;
		failed += r.error != CYCLE_OK;
#if WEEK7_CONSOLE
		if (verbose) {
			print_cycle(i, &r);
		}
#else
		ARG_UNUSED(verbose);
#endif
		k_msleep(CONFIG_WEEK7_CYCLE_GAP_MS);
	}
#if WEEK7_CONSOLE
	printk("CYCLES END ok=%u failed=%u\r\n", ok, failed);
#else
	ARG_UNUSED(ok);
	ARG_UNUSED(failed);
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
#if WEEK7_CONSOLE
	if (verbose) {
		struct link_info li;
		link_get_info(&li);
		printk("SESSION link att_mtu=%u interval_1250us=%u latency=%u phy_tx=%u\r\n",
		       li.att_mtu, li.interval_1250us, li.latency, li.tx_phy);
	}
#endif
	k_sleep(K_SECONDS(CONFIG_WEEK7_CONNECTED_IDLE_S));
	run_cycles(session_nonce_ready ? CONFIG_WEEK7_P1_CYCLES : 0, CONFIG_WEEK7_P0_CYCLES, verbose);
	(void)link_disconnect();
}
#endif /* !CONFIG_WEEK7_BENCH */

#if defined(CONFIG_WEEK7_ENERGY_USB)
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

/* TC4: q/scale of the selected kernel vs the SV3 golden, requests vs the Python reference.
 * P1 uses the PUBLIC_TEST_ONLY key 00..1f with sequence n+1 (never the bench key). */
static void verify_split(unsigned split)
{
	static uint8_t frame[FRAG_MAX_FRAME];
	uint8_t public_key[32], nonce[12];
	for (unsigned i = 0; i < sizeof(public_key); ++i) {
		public_key[i] = (uint8_t)i;
	}
	for (unsigned n = 0; n < 20u; ++n) {
		struct pipeline_tensor t;
		char q_hex[65], s_hex[65], r_hex[65];
		if (pipeline_head(split, n, &t) != 0) {
			printk("VQ n=%u s=%u ERROR\r\n", n, split);
			continue;
		}
		hex_digest(t.q, (size_t)t.channels * t.length, q_hex);
		hex_digest(t.scale_le, 2u * t.channels, s_hex);
		printk("VQ n=%u s=%u C=%u L=%u q_sha256=%s scale_sha256=%s\r\n", n, split, t.channels,
		       t.length, q_hex, s_hex);
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
}

static void command_verify(int argc, char **argv)
{
	uint32_t split = 0;
	if (argc == 2 && strcmp(argv[1], "ALL") == 0) {
		for (unsigned s = 0; s < 11u; ++s) {
			verify_split(s);
		}
	} else if (argc == 2 && parse_u32(argv[1], &split) && split < 11u) {
		verify_split(split);
	} else {
		printk("ERROR usage VERIFY <s>|ALL\r\n");
		return;
	}
	printk("VERIFY END kernel=%s\r\n", KERNEL_NAME);
}
#endif /* CONFIG_WEEK7_ENERGY_USB */

/* ------------------------------------------------------------------ banner / dispatch */

#if WEEK7_CONSOLE
static void print_banner(void)
{
	printk("READY WEEK7 build=%s variant=%s kernel=%s split=%u p1=%u p0=%u gap_ms=%u "
	       "boot_idle_s=%u connected_idle_s=%u ctrl_min_us=%u timeout_ms=%u conn_interval_1250us=%u "
	       "d4_pin=P0.%u\r\n",
	       WEEK7_BUILD_ID, WEEK7_VARIANT, KERNEL_NAME, CONFIG_WEEK7_SPLIT,
	       CONFIG_WEEK7_P1_CYCLES, CONFIG_WEEK7_P0_CYCLES, CONFIG_WEEK7_CYCLE_GAP_MS,
	       CONFIG_WEEK7_BOOT_IDLE_S, CONFIG_WEEK7_CONNECTED_IDLE_S, CONFIG_WEEK7_CTRL_MIN_US,
	       CONFIG_WEEK7_RESPONSE_TIMEOUT_MS, CONFIG_WEEK7_CONN_INTERVAL_1250US, MARKER_CTRL_PIN);
#if defined(CONFIG_WEEK7_ENERGY_USB)
	print_nonce();
	print_link();
#endif
}

static void print_help(void)
{
	printk("COMMANDS HELP | STATUS | STACK | MARKERS | REBOOT\r\n");
#if defined(CONFIG_WEEK7_BENCH)
	printk("COMMANDS CMP ALL | CMP MIX | BENCH W4|FAST <s> | BENCH ALL\r\n");
#else
	printk("COMMANDS NONCE | CONNPARAM <min> <max> | VERIFY <s>|ALL | CYCLES <n_p1> <n_p0> | SESSION\r\n");
#endif
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
#if defined(CONFIG_WEEK7_BENCH)
	} else if (strcmp(cmd, "CMP") == 0 && argc == 2 && strcmp(argv[1], "ALL") == 0) {
		cmp_all();
		print_stacks();
	} else if (strcmp(cmd, "CMP") == 0 && argc == 2 && strcmp(argv[1], "MIX") == 0) {
		cmp_mix();
	} else if (strcmp(cmd, "BENCH") == 0) {
		command_bench(argc, argv);
#else
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
	} else if (strcmp(cmd, "VERIFY") == 0) {
		command_verify(argc, argv);
	} else if (strcmp(cmd, "CYCLES") == 0) {
		/* Same order as the energy session: n_p1 P1 cycles, then n_p0 P0 cycles. */
		uint32_t n1 = 0, n0 = 0;
		if (argc == 3 && parse_u32(argv[1], &n1) && parse_u32(argv[2], &n0) &&
		    n1 < NONCE_RESERVE_BLOCK && n0 <= 1000u && n1 + n0 > 0u) {
			if (!link_ready()) {
				printk("ERROR link not ready (start week7_stub_edge.py)\r\n");
			} else if (n1 > 0u && !session_nonce_ready) {
				printk("ERROR nonce not READY: P1 refused\r\n");
			} else {
				printk("CYCLES BEGIN p1=%u p0=%u\r\n", n1, n0);
				run_cycles(n1, n0, true);
				print_nonce();
				print_stacks();
			}
		} else {
			printk("ERROR usage CYCLES <n_p1> <n_p0>\r\n");
		}
	} else if (strcmp(cmd, "SESSION") == 0) {
		printk("SESSION BEGIN p1=%u p0=%u\r\n",
		       session_nonce_ready ? CONFIG_WEEK7_P1_CYCLES : 0, CONFIG_WEEK7_P0_CYCLES);
		session_after_idle(true);
		print_nonce();
		print_stacks();
		printk("SESSION END\r\n");
#endif
	} else {
		printk("ERROR unknown command (HELP)\r\n");
	}
}
#endif /* WEEK7_CONSOLE */

/* ------------------------------------------------------------------ main */

int main(void)
{
	if (markers_init() != 0 || marker_ctrl_init() != 0) {
		return -1;
	}
	leds_off();
	dwt_init();
	__asm__ volatile("" : : "r"(build_id) : "memory");
#if !defined(CONFIG_WEEK7_BENCH)
	nonce_nvs_init();
	session_nonce_ready = nonce_prepare();
#endif

#if defined(CONFIG_WEEK7_ENERGY)
	k_msleep(100);
	if (CONFIG_WEEK7_P1_CYCLES > 0 && !session_nonce_ready) {
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
	energy_cycle_init();   /* after link_init(): it resets the reassembler's stream mask */
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
#if defined(CONFIG_WEEK7_ENERGY_USB)
	const int bt_err = link_init();
	energy_cycle_init();   /* after link_init(): it resets the reassembler's stream mask */
#endif
	bool connected_before = false;
	for (;;) {
		uint32_t dtr = 0;
		const bool connected =
			uart_line_ctrl_get(console_device, UART_LINE_CTRL_DTR, &dtr) == 0 && dtr;
		if (connected && !connected_before) {
			k_msleep(100);
			print_banner();
#if defined(CONFIG_WEEK7_ENERGY_USB)
			printk("BOOT bt_enable=%d nonce_session_ready=%u\r\n", bt_err, session_nonce_ready);
#endif
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
