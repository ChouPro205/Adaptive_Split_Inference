/* Week 4 R3: one runtime-selected head, separate from Week 3 entry point. */
#include "week4_head.h"
#include "week4_inputs.h"
#include "week4_protocol.h"
#include "markers.h"

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include <cmsis_core.h>
#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/irq.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#define WARMUP_COUNT 20U
#define MEASURE_COUNT 100U

BUILD_ASSERT(DT_NODE_HAS_COMPAT(DT_CHOSEN(zephyr_console), zephyr_cdc_acm_uart),
	     "Week 4 requires USB CDC ACM");
static const struct device *const console_device = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));
static uint32_t measured_cycles[MEASURE_COUNT];
static bool dwt_ready;

static inline uint32_t cycle_count(void)
{
	__asm__ volatile("" ::: "memory");
	uint32_t cycles = DWT->CYCCNT;
	__asm__ volatile("" ::: "memory");
	return cycles;
}

static bool init_dwt(void)
{
	CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
	DWT->CYCCNT = 0;
	DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
	__DSB();
	__ISB();
	for (unsigned i = 0; i < 8; ++i) {
		__asm__ volatile("nop" ::: "memory");
	}
	return (DWT->CTRL & DWT_CTRL_NOCYCCNT_Msk) == 0 && DWT->CYCCNT != 0;
}

static void dump_tensor(unsigned sample, unsigned split, const struct week4_result *result)
{
	const struct week4_shape *shape = &result->shape;
	printk("TENSOR %u %s %u FP32 %s %u", sample, week4_sample_ids[sample], split,
	       shape->rank == 3U ? "NCL" : "NC", shape->rank);
	for (unsigned i = 0; i < shape->rank; ++i) {
		printk(" %u", shape->dims[i]);
	}
	printk(" %u\r\n", shape->count);
	for (unsigned i = 0; i < shape->count; ++i) {
		uint32_t bits;
		memcpy(&bits, &result->values[i], sizeof(bits));
		printk("%08x", bits);
		if (i % 16U == 15U || i + 1U == shape->count) {
			printk("\r\n");
			/* Retain Week 3's verified USB worker pacing. */
			k_msleep(5);
		} else {
			printk(" ");
		}
	}
	printk("END %u %u\r\n", sample, split);
}

static int measure_head(unsigned sample, unsigned split, struct week4_result *result,
			uint32_t *elapsed)
{
	/* GPIO writes and USB output are outside the cycle interval. Disable IRQs
	 * only for one head run to isolate compute; re-enable between iterations.
	 * No baseline subtraction: s=0 measures the identity/API bookkeeping.
	 * uint32 subtraction handles one wrap (67.1 s at 64 MHz).
	 */
	marker_on(MARKER_HEAD);
	unsigned key = irq_lock();
	uint32_t start = cycle_count();
	int status = week4_run_head(split, week4_inputs[sample], result);
	uint32_t end = cycle_count();
	irq_unlock(key);
	marker_off(MARKER_HEAD);
	*elapsed = end - start;
	return status;
}

static void process_command(const struct week4_command *command)
{
	unsigned sample = command->sample;
	unsigned split = command->split;
	bool bench = command->type == WEEK4_BENCH;
	struct week4_result result;
	if (bench && !dwt_ready) {
		printk("ERROR DWT unavailable\r\n");
		return;
	}
	printk("BEGIN %u %s %u %s\r\n", sample, week4_sample_ids[sample], split,
	       bench ? "BENCH" : "RUN");
	if (bench) {
		uint32_t unused;
		for (unsigned i = 0; i < WARMUP_COUNT; ++i) {
			if (measure_head(sample, split, &result, &unused) != 0) {
				printk("ERROR head warmup\r\n");
				return;
			}
		}
		for (unsigned i = 0; i < MEASURE_COUNT; ++i) {
			if (measure_head(sample, split, &result, &measured_cycles[i]) != 0) {
				printk("ERROR head measurement\r\n");
				return;
			}
		}
		/* All USB/logging starts after the entire measurement batch. */
		printk("TIMING %u %s %u warmup=%u measured=%u cpu_hz=%u irq=locked baseline=raw\r\n",
		       sample, week4_sample_ids[sample], split, WARMUP_COUNT, MEASURE_COUNT,
		       SystemCoreClock);
		for (unsigned i = 0; i < MEASURE_COUNT; ++i) {
			printk("CYCLES %u %u %u %u\r\n", sample, split, i, measured_cycles[i]);
			if (i % 16U == 15U) {
				k_msleep(5);
			}
		}
	} else {
		marker_on(MARKER_HEAD);
		int status = week4_run_head(split, week4_inputs[sample], &result);
		marker_off(MARKER_HEAD);
		if (status != 0) {
			printk("ERROR head\r\n");
			return;
		}
	}
	dump_tensor(sample, split, &result);
	size_t unused_stack;
	if (k_thread_stack_space_get(k_current_get(), &unused_stack) == 0) {
		size_t size = k_current_get()->stack_info.size;
		printk("STACK main_peak_bytes=%u main_size_bytes=%u\r\n",
		       (unsigned)(size - unused_stack), (unsigned)size);
	}
	printk("DONE %u %u %s\r\n", sample, split, bench ? "BENCH" : "RUN");
}

int main(void)
{
	char line[48];
	unsigned length = 0;
	bool discard = false;
	bool connected_before = false;
	if (!device_is_ready(console_device) || markers_init() != 0) {
		return -1;
	}
	/* Both fixes from Week 3: TX backpressure and initial USB OUT arming. */
	struct uart_config uart_cfg = {
		.baudrate = 115200,
		.parity = UART_CFG_PARITY_NONE,
		.stop_bits = UART_CFG_STOP_BITS_1,
		.data_bits = UART_CFG_DATA_BITS_8,
		.flow_ctrl = UART_CFG_FLOW_CTRL_RTS_CTS,
	};
	if (uart_configure(console_device, &uart_cfg) != 0) {
		return -1;
	}
	uart_irq_rx_enable(console_device);
	dwt_ready = init_dwt();
	while (true) {
		uint32_t dtr = 0;
		bool connected = uart_line_ctrl_get(console_device, UART_LINE_CTRL_DTR, &dtr) == 0 && dtr != 0;
		if (connected && !connected_before) {
			k_msleep(100);
			printk("READY WEEK4 R3 %s samples=20 splits=11 DWT=%s\r\n",
			       WEEK4_MANIFEST_SHA256, dwt_ready ? "READY" : "ERROR");
			printk("COMMAND RUN n s or BENCH n s (n=0..19 s=0..10)\r\n");
			length = 0;
			discard = false;
		}
		if (connected) {
			unsigned char byte;
			while (uart_poll_in(console_device, &byte) == 0) {
				if (byte == '\n') {
					line[length] = '\0';
					struct week4_command command;
					if (!discard && week4_parse_command(line, &command) == 0) {
						process_command(&command);
					} else {
						printk("ERROR expected RUN n s or BENCH n s (n=0..19 s=0..10)\r\n");
					}
					length = 0;
					discard = false;
				} else if (byte != '\r' && !discard) {
					if (byte == '\0' || length + 1U >= sizeof(line)) {
						discard = true; /* Reject the entire line, including its suffix. */
					} else {
						line[length++] = (char)byte;
					}
				}
			}
		} else {
			length = 0;
			discard = false;
		}
		connected_before = connected;
		k_msleep(10);
	}
	return 0;
}
