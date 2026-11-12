/*
 * Week 10 Device firmware, E_prot of P1 at every s with the radio off (decisions W10-D1, W10-D2; criteria
 * TC1/TC2/TC4 in the week 10 plan until the week 10 report). Fork of week9/main.c (hash-locked) with the NVS
 * nonce store of week8/main.c (hash-locked) and no radio: the cycle is prot_cycle.c at the (split, op) of the
 * W10-D1 plan (week10_prot_plan.h, 50 rounds x 21 cycles, round k = W8-D3 sample k).
 *
 * prot-usb  USB CDC, radio off, NVS nonce: VERIFY ALL | VERIFY <s> (q/scale SHA-256 of the 50 samples, protect()
 *           with the PUBLIC_TEST key and sequence n + 1, the HEAD-only s1 output), TPROT (DWT of descriptor +
 *           protect per s, IRQs locked), TCONV (DWT of the HEAD-only s1 cycle), NONCE, ONE, SESSION dry run.
 *           No nonce block at boot: the first P1 command reserves one, so NONCE right after boot reads the
 *           value the previous image left. Powered by the laptop: timings are debug evidence only.
 * prot      no USB/console/LED, no radio: at power-on runs the PPK2 session by itself:
 *           nonce block reserved (one D1 pulse) + plan self-check -> self-test D0..D4 -> idle 30 s ->
 *           1050 plan cycles, CONFIG_WEEK10_CYCLE_GAP_MS apart -> sleep.
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

#include "marker_ctrl.h"
#include "markers.h"
#include "nonce_nvs.h"
#include "packets.h"
#include "prot_cycle.h"
#include "sha256.h"
#include "week10_build.h"

#if defined(CONFIG_BT)
#error "Week 10 E_prot images have no radio (W10-D1)"
#endif

#if defined(CONFIG_WEEK10_PROT_USB)
#define WEEK10_CONSOLE 1
#include <zephyr/drivers/uart.h>
#include <zephyr/sys/reboot.h>
BUILD_ASSERT(DT_NODE_HAS_COMPAT(DT_CHOSEN(zephyr_console), zephyr_cdc_acm_uart),
	     "prot-usb uses USB CDC ACM as control/debug console");
static const struct device *const console_device = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));
#else
#define WEEK10_CONSOLE 0
BUILD_ASSERT(!IS_ENABLED(CONFIG_PRINTK) && !IS_ENABLED(CONFIG_USB_DEVICE_STACK_NEXT) &&
	     !IS_ENABLED(CONFIG_SERIAL), "prot image: no USB, console or printk (TC1)");
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
	prot_plan_digest(hex);
	return strcmp(hex, prot_plan_sha256()) == 0;
}

/* ------------------------------------------------------------------ nonce */

static bool block_reserved;
static uint64_t boot_reserved_sequence;

/* Reserve one sequence block now (one NVS write, one D1 pulse) so that no cycle ever writes Flash (W7-D2).
 * The sequence used to trigger it is discarded: skipping is always safe. */
static bool nonce_prepare(void)
{
	uint8_t nonce[12];
	struct nonce_nvs_info info;
	nonce_nvs_get_info(&info);
	if (info.status != NONCE_READY) {
		return false;
	}
	block_reserved = nonce_nvs_allocate(&boot_reserved_sequence, nonce) == 0;
	return block_reserved;
}

#if defined(CONFIG_WEEK10_PROT_USB)
/* Sequences left in the reserved block without a Flash write. */
static uint64_t nonce_left(void)
{
	struct nonce_nvs_info info;
	nonce_nvs_get_info(&info);
	if (info.status != NONCE_READY || !block_reserved || info.next > info.limit) {
		return 0;
	}
	return info.limit - info.next + 1u;
}
#endif

/* ------------------------------------------------------------------ console (prot-usb) */

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

static void hex_digest(const void *data, size_t length, char out[65])
{
	uint8_t digest[32];
	sha256(data, length, digest);
	sha256_hex(digest, out);
}

static void print_cycle(const struct prot_result *r)
{
	char digest[65] = "-";
	if (r->op == PROT_OP_P1 && r->error == PROT_OK) {
		sha256_hex(r->digest, digest);
	}
	printk("CYCLE i=%u round=%u n=%u id=%s s=%u op=%s seq=%llu bytes=%u ctrl_cyc=%u head_cyc=%u "
	       "quant_cyc=%u prot_cyc=%u head_us=%u prot_us=%u nonce_writes=%u res=%s prot_sha256=%s\r\n",
	       r->cycle, r->cycle / (2u * PROT_SPLITS + 1u), r->sample, prot_sample_id(r->sample), r->split,
	       prot_op_names[r->op < PROT_OP_COUNT ? r->op : 0], (unsigned long long)r->sequence, r->bytes_payload,
	       r->ctrl_cycles, r->head_cycles, r->quant_cycles, r->prot_cycles, r->head_cycles / (CPU_HZ / 1000000u),
	       r->prot_cycles / (CPU_HZ / 1000000u), r->nonce_writes, prot_error_names[r->error], digest);
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
	       "sender_id=%u key_check=%02x%02x%02x%02x%02x%02x%02x%02x writes=%u block_reserved=%u "
	       "boot_reserved_sequence=%llu left=%llu\r\n",
	       nonce_status_name(ni.status), nonce_reason_names[ni.reason], ni.persisted, ni.next, ni.limit,
	       ni.key_id, ni.sender_id, ni.kcv[0], ni.kcv[1], ni.kcv[2], ni.kcv[3], ni.kcv[4], ni.kcv[5], ni.kcv[6],
	       ni.kcv[7], ni.writes, block_reserved, boot_reserved_sequence, nonce_left());
}

/* P1 cycles need a READY store and room in the reserved block (reserve it now if this boot has none). */
static bool p1_allowed(unsigned p1_cycles)
{
	if (p1_cycles == 0u) {
		return true;
	}
	if (!block_reserved && !nonce_prepare()) {
		printk("ERROR nonce not READY: P1 refused\r\n");
		return false;
	}
	if (nonce_left() < p1_cycles) {
		printk("ERROR nonce block has %llu sequences left, %u P1 cycles need more (REBOOT)\r\n",
		       (unsigned long long)nonce_left(), p1_cycles);
		return false;
	}
	return true;
}

/* TC2: per sample at one split, q/scale vs the host references and protect() with the PUBLIC_TEST_ONLY
 * key 00..1f and sequence n + 1 (never the bench key) vs contracts/i2_ref. */
static void verify_split(unsigned split)
{
	static uint8_t out[PROT_MAX_VALUES];
	uint8_t public_key[32], nonce[12];
	for (unsigned i = 0; i < sizeof(public_key); ++i) {
		public_key[i] = (uint8_t)i;
	}
	for (unsigned n = 0; n < prot_sample_count(); ++n) {
		struct prot_tensor t;
		char q_hex[65], s_hex[65], p_hex[65];
		if (prot_head(split, n, &t, NULL) != 0) {
			printk("VQ n=%u s=%u ERROR\r\n", n, split);
			continue;
		}
		hex_digest(t.q, (size_t)t.channels * t.length, q_hex);
		hex_digest(t.scale_le, 2u * t.channels, s_hex);
		printk("VQ n=%u id=%s s=%u C=%u L=%u bytes=%u q_sha256=%s scale_sha256=%s\r\n", n, prot_sample_id(n),
		       split, t.channels, t.length, (unsigned)(t.channels * t.length + 2u * t.channels), q_hex, s_hex);
		pace();
		const uint64_t sequence = n + 1u;
		for (unsigned i = 0; i < 4u; ++i) {
			nonce[i] = (uint8_t)((uint32_t)PKT_SENDER_ID >> (8u * i));
		}
		for (unsigned i = 0; i < 8u; ++i) {
			nonce[4u + i] = (uint8_t)(sequence >> (8u * i));
		}
		uint32_t cycles = 0;
		const i2_status status = prot_protect(&t, public_key, nonce, out, sizeof(out), &cycles);
		hex_digest(out, (size_t)t.channels * t.length, p_hex);
		printk("VPROT n=%u s=%u seq=%u status=%d len=%u sha256=%s prot_cyc=%u\r\n", n, split, n + 1u,
		       (int)status, (unsigned)(t.channels * t.length), p_hex, cycles);
		pace();
	}
}

/* W10-D2: the HEAD-only s1 output (16 x 360 FP32) of every sample vs the host shim. */
static void verify_conv(void)
{
	for (unsigned n = 0; n < prot_sample_count(); ++n) {
		const float *values;
		unsigned count;
		char hex[65];
		if (prot_conv(n, &values, &count) != 0) {
			printk("VCONV n=%u ERROR\r\n", n);
			continue;
		}
		hex_digest(values, count * sizeof(float), hex);
		printk("VCONV n=%u s=%u values=%u sha256=%s\r\n", n, PROT_CONV_SPLIT, count, hex);
		pace();
	}
}

/* TC2: DWT of descriptor + protect() (PUBLIC_TEST key, no nonce allocation) at one split, week 9 TDEV method:
 * 20 warm-up runs on sample 0, IRQs locked for each run, printing outside, then the 50 samples. */
#define TWARMUP 20u

static void tprot_split(unsigned split)
{
	static uint8_t out[PROT_MAX_VALUES];
	uint8_t public_key[32], nonce[12] = {0};
	for (unsigned i = 0; i < sizeof(public_key); ++i) {
		public_key[i] = (uint8_t)i;
	}
	uint64_t sum = 0;
	uint32_t lo = UINT32_MAX, hi = 0;
	const unsigned runs = prot_sample_count();
	for (unsigned i = 0; i < TWARMUP + runs; ++i) {
		const unsigned n = i < TWARMUP ? 0u : i - TWARMUP;
		struct prot_tensor t;
		if (prot_head(split, n, &t, NULL) != 0) {
			printk("TP s=%u n=%u ERROR\r\n", split, n);
			return;
		}
		nonce[4] = (uint8_t)(n + 1u);
		uint32_t cycles = 0;
		const unsigned key = irq_lock();
		const i2_status status = prot_protect(&t, public_key, nonce, out, sizeof(out), &cycles);
		irq_unlock(key);
		if (status != I2_OK) {
			printk("TP s=%u n=%u ERROR status=%d\r\n", split, n, (int)status);
			return;
		}
		if (i < TWARMUP) {
			continue;
		}
		printk("TP s=%u n=%u prot_cyc=%u bytes=%u\r\n", split, n, cycles, (unsigned)(t.channels * t.length));
		sum += cycles;
		lo = MIN(lo, cycles);
		hi = MAX(hi, cycles);
		if (n % 16u == 15u) {
			pace();
		}
	}
	printk("TPSUM s=%u runs=%u warmup=%u irq=locked cpu_hz=%u prot_min=%u prot_max=%u prot_mean_x100=%llu\r\n",
	       split, runs, TWARMUP, SystemCoreClock, lo, hi, (unsigned long long)(sum * 100u / runs));
	pace();
}

/* W10-D2: DWT of the HEAD-only s1 cycle body (head_fast_run to s1, no quantization), same method. */
static void tconv(void)
{
	uint64_t sum = 0;
	uint32_t lo = UINT32_MAX, hi = 0;
	const unsigned runs = prot_sample_count();
	for (unsigned i = 0; i < TWARMUP + runs; ++i) {
		const unsigned n = i < TWARMUP ? 0u : i - TWARMUP;
		const float *values;
		unsigned count;
		const unsigned key = irq_lock();
		const uint32_t start = prot_cycle_now();
		const int status = prot_conv(n, &values, &count);
		const uint32_t cycles = prot_cycle_now() - start;
		irq_unlock(key);
		if (status != 0) {
			printk("TC n=%u ERROR\r\n", n);
			return;
		}
		if (i < TWARMUP) {
			continue;
		}
		printk("TC n=%u conv_cyc=%u\r\n", n, cycles);
		sum += cycles;
		lo = MIN(lo, cycles);
		hi = MAX(hi, cycles);
		if (n % 16u == 15u) {
			pace();
		}
	}
	printk("TCSUM s=%u runs=%u warmup=%u irq=locked cpu_hz=%u conv_min=%u conv_max=%u conv_mean_x100=%llu\r\n",
	       PROT_CONV_SPLIT, runs, TWARMUP, SystemCoreClock, lo, hi, (unsigned long long)(sum * 100u / runs));
}

/* ------------------------------------------------------------------ banner / dispatch */

static void print_banner(void)
{
	char hex[65];
	prot_plan_digest(hex);
	printk("READY WEEK10 build=%s variant=%s kernel=%s rounds=%u cycles=%u samples=%u p1_cycles=%u gap_ms=%u "
	       "boot_idle_s=%u ctrl_min_us=%u selftest_ms=%u d4_pin=P0.%u set_sha256=%s plan_sha256=%s "
	       "plan_device_sha256=%s plan_ok=%u\r\n",
	       WEEK10_BUILD_ID, WEEK10_VARIANT, KERNEL_NAME, prot_sample_count(), prot_plan_cycles(),
	       prot_sample_count(), prot_plan_p1_cycles(0, prot_plan_cycles()), CONFIG_WEEK10_CYCLE_GAP_MS,
	       CONFIG_WEEK10_BOOT_IDLE_S, CONFIG_WEEK10_CTRL_MIN_US, CONFIG_WEEK10_SELFTEST_MS, MARKER_CTRL_PIN,
	       prot_set_sha256(), prot_plan_sha256(), hex, strcmp(hex, prot_plan_sha256()) == 0);
	print_nonce();
}

static void print_help(void)
{
	printk("COMMANDS HELP | STATUS | STACK | MARKERS | REBOOT | NONCE\r\n");
	printk("COMMANDS VERIFY ALL | VERIFY <s> | TPROT ALL | TPROT <s> | TCONV | ONE <n> <s> P1|P0 | "
	       "ONE <n> CONV | SESSION [gap_ms] [first] [count]\r\n");
}

static bool parse_split(const char *text, uint32_t *split)
{
	return parse_u32(text, split) && *split < PROT_SPLITS;
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
	} else if (strcmp(cmd, "NONCE") == 0) {
		print_nonce();
	} else if (strcmp(cmd, "MARKERS") == 0) {
		markers_selftest();
		printk("MARKERS END order=D0,D1,D2,D3,D4 width_ms=%u\r\n", CONFIG_WEEK10_SELFTEST_MS);
	} else if (strcmp(cmd, "REBOOT") == 0) {
		printk("REBOOT\r\n");
		k_msleep(100);
		sys_reboot(SYS_REBOOT_COLD);
	} else if (strcmp(cmd, "VERIFY") == 0 && argc == 2 &&
		   (strcmp(argv[1], "ALL") == 0 || parse_split(argv[1], &a))) {
		const bool all = strcmp(argv[1], "ALL") == 0;
		for (unsigned s = all ? 0u : a; s < (all ? PROT_SPLITS : a + 1u); ++s) {
			verify_split(s);
		}
		if (all) {
			verify_conv();
		}
		printk("VERIFY END kernel=%s samples=%u splits=%s set_sha256=%s\r\n", KERNEL_NAME,
		       prot_sample_count(), all ? "ALL" : argv[1], prot_set_sha256());
	} else if (strcmp(cmd, "TPROT") == 0 && argc == 2 &&
		   (strcmp(argv[1], "ALL") == 0 || parse_split(argv[1], &a))) {
		const bool all = strcmp(argv[1], "ALL") == 0;
		for (unsigned s = all ? 0u : a; s < (all ? PROT_SPLITS : a + 1u); ++s) {
			tprot_split(s);
		}
		printk("TPROT END kernel=%s splits=%s\r\n", KERNEL_NAME, all ? "ALL" : argv[1]);
	} else if (strcmp(cmd, "TCONV") == 0 && argc == 1) {
		tconv();
		printk("TCONV END kernel=%s\r\n", KERNEL_NAME);
	} else if (strcmp(cmd, "ONE") == 0) {
		struct prot_result r;
		if (argc == 3 && parse_u32(argv[1], &a) && a < prot_sample_count() && strcmp(argv[2], "CONV") == 0) {
			printk("ONE BEGIN n=%u op=CONV\r\n", a);
			prot_cycle_run(PROT_CONV_SPLIT, a, PROT_OP_CONV, &r);
		} else if (argc == 4 && parse_u32(argv[1], &a) && a < prot_sample_count() && parse_split(argv[2], &b) &&
			   (strcmp(argv[3], "P1") == 0 || strcmp(argv[3], "P0") == 0)) {
			const bool p1 = strcmp(argv[3], "P1") == 0;
			if (!p1_allowed(p1 ? 1u : 0u)) {
				return;
			}
			printk("ONE BEGIN n=%u s=%u op=%s\r\n", a, b, argv[3]);
			prot_cycle_run(b, a, p1 ? PROT_OP_P1 : PROT_OP_P0, &r);
		} else {
			printk("ERROR usage ONE <n 0..%u> <s 0..9> P1|P0 | ONE <n> CONV\r\n", prot_sample_count() - 1u);
			return;
		}
		print_cycle(&r);
		printk("ONE END ok=%u\r\n", r.error == PROT_OK && r.nonce_writes == 0u);
	} else if (strcmp(cmd, "SESSION") == 0) {
		/* Dry run of the plan's cycles (no self-test, no idle window); P1 uses the reserved block. */
		a = CONFIG_WEEK10_CYCLE_GAP_MS;
		b = 0;
		c = prot_plan_cycles();
		if (argc <= 4 && (argc < 2 || parse_u32(argv[1], &a)) && (argc < 3 || parse_u32(argv[2], &b)) &&
		    (argc < 4 || parse_u32(argv[3], &c)) && a <= 10000u && b < prot_plan_cycles() && c >= 1u &&
		    c <= prot_plan_cycles() - b) {
			if (!plan_ok()) {
				printk("ERROR plan bytes differ from plan_sha256\r\n");
				return;
			}
			if (!p1_allowed(prot_plan_p1_cycles(b, c))) {
				return;
			}
			printk("SESSION BEGIN first=%u count=%u gap_ms=%u plan_sha256=%s\r\n", b, c, a, prot_plan_sha256());
			unsigned ok = 0;
			for (unsigned i = b; i < b + c; ++i) {
				struct prot_result r;
				prot_cycle_run_plan(i, &r);
				ok += r.error == PROT_OK && r.nonce_writes == 0u;
				print_cycle(&r);
				k_msleep(a);
			}
			print_nonce();
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
	prot_cycle_init();
	nonce_nvs_init();

#if defined(CONFIG_WEEK10_PROT)
	const bool ready = nonce_prepare();   /* the only Flash write of the session: one D1 pulse */
	k_msleep(100);
	if (!ready || !plan_ok()) {
		/* No nonce or plan bytes differ from WEEK10_PROT_PLAN_SHA256: never protect, no session.
		 * Ten 5 ms CTRL pulses mark the refusal on the trace. */
		for (unsigned i = 0; i < 10u; ++i) {
			marker_ctrl_on();
			k_msleep(5);
			marker_ctrl_off();
			k_msleep(45);
		}
		k_sleep(K_FOREVER);
	}
	markers_selftest();
	k_sleep(K_SECONDS(CONFIG_WEEK10_BOOT_IDLE_S));   /* W7-D3: idle window */
	for (unsigned i = 0; i < prot_plan_cycles(); ++i) {
		struct prot_result r;
		prot_cycle_run_plan(i, &r);
		k_msleep(CONFIG_WEEK10_CYCLE_GAP_MS);
	}
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
			printk("BOOT plan_ok=%u nonce_block_at_boot=0\r\n", plan_ok());
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
