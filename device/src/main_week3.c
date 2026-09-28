/* Week 3 v2 FP32 head, USB CDC tensor capture. */

#include "week3_head.h"
#include "week3_inputs.h"
#include "markers.h"

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

BUILD_ASSERT(DT_NODE_HAS_COMPAT(DT_CHOSEN(zephyr_console), zephyr_cdc_acm_uart),
	     "Week 3 requires the USB CDC ACM console");

static const struct device *const console_device = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));
static float activation_a[WEEK3_ACTIVATION_COUNT];
static float activation_b[WEEK3_ACTIVATION_COUNT];

static void dump_tensor(unsigned sample, const char *name, const float *values, unsigned count)
{
	printk("TENSOR %u %s %u\r\n", sample, name, count);
	for (unsigned i = 0; i < count; ++i) {
		uint32_t bits;
		memcpy(&bits, &values[i], sizeof(bits));
		printk("%08x", bits);
		if (i % 16U == 15U || i + 1U == count) {
			printk("\r\n");
			/* Allow the USB CDC TX worker to drain between lines. An unpaced
			 * tensor burst stalled reproducibly in the final P2 rows of RUN 10/11.
			 */
			k_msleep(5);
		} else {
			printk(" ");
		}
	}
	printk("END %s\r\n", name);
}

static void run_sample(unsigned sample, bool trace)
{
	const float *m0 = week3_inputs[sample];
	printk("BEGIN %u %s\r\n", sample, trace ? "TRACE" : "RUN");
	marker_on(MARKER_HEAD);
	week3_conv1(m0, activation_a);
	marker_off(MARKER_HEAD);
	if (trace) {
		dump_tensor(sample, "M1", activation_a, WEEK3_ACTIVATION_COUNT);
	}
	week3_relu(activation_a, WEEK3_ACTIVATION_COUNT);
	if (trace) {
		dump_tensor(sample, "R1", activation_a, WEEK3_ACTIVATION_COUNT);
	}
	marker_on(MARKER_HEAD);
	week3_conv2(activation_a, activation_b);
	marker_off(MARKER_HEAD);
	if (trace) {
		dump_tensor(sample, "M2", activation_b, WEEK3_ACTIVATION_COUNT);
	}
	week3_relu(activation_b, WEEK3_ACTIVATION_COUNT);
	if (trace) {
		dump_tensor(sample, "R2", activation_b, WEEK3_ACTIVATION_COUNT);
	}
	week3_pool(activation_b, activation_a);
	dump_tensor(sample, "P2", activation_a, WEEK3_P2_COUNT);
	size_t unused_stack;
	int stack_result = k_thread_stack_space_get(k_current_get(), &unused_stack);
	if (stack_result == 0) {
		size_t total_stack = k_current_get()->stack_info.size;
		printk("STACK main_peak_bytes=%u main_size_bytes=%u\r\n",
		       (unsigned)(total_stack - unused_stack), (unsigned)total_stack);
	} else {
		printk("STACK ERROR %d\r\n", stack_result);
	}
	printk("DONE %u\r\n", sample);
}

static bool parse_sample(const char *line, const char *prefix, unsigned *sample)
{
	size_t length = strlen(prefix);
	if (strncmp(line, prefix, length) != 0 || line[length] != ' ') {
		return false;
	}
	const char *digits = line + length + 1;
	if (*digits == '\0') {
		return false;
	}
	unsigned value = 0;
	for (; *digits != '\0'; ++digits) {
		if (*digits < '0' || *digits > '9') {
			return false;
		}
		value = value * 10U + (unsigned)(*digits - '0');
		if (value >= WEEK3_SAMPLE_COUNT) {
			return false;
		}
	}
	*sample = value;
	return true;
}

static void process_line(const char *line)
{
	unsigned sample;
	if (parse_sample(line, "TRACE", &sample)) {
		run_sample(sample, true);
	} else if (parse_sample(line, "RUN", &sample)) {
		run_sample(sample, false);
	} else {
		printk("ERROR expected TRACE n or RUN n, 0 <= n < 20\r\n");
	}
}

int main(void)
{
	char line[32];
	unsigned length = 0;
	bool connected_before = false;
	if (!device_is_ready(console_device) || markers_init() != 0) {
		return -1;
	}
	/* CDC ACM poll_out discards bytes when its TX ring fills without flow
	 * control. This enables the driver's internal blocking backpressure.
	 */
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
	/* The NCS CDC ACM driver arms its first USB OUT transfer on RX enable.
	 * poll_in() only drains the RX ring and cannot arm that first transfer.
	 */
	uart_irq_rx_enable(console_device);
	while (true) {
		uint32_t dtr = 0;
		bool connected = uart_line_ctrl_get(console_device, UART_LINE_CTRL_DTR, &dtr) == 0 && dtr != 0;
		if (connected && !connected_before) {
			k_msleep(100);
			printk("READY WEEK3 mitdb-week3-fp32-20260925-v2 P2 1x16x180\r\n");
			printk("COMMAND TRACE n or RUN n (0..19)\r\n");
			length = 0;
		}
		if (connected) {
			unsigned char byte;
			while (uart_poll_in(console_device, &byte) == 0) {
				if (byte == '\n') {
					line[length] = '\0';
					process_line(line);
					length = 0;
				} else if (byte != '\r') {
					if (length + 1U < sizeof(line)) {
						line[length++] = (char)byte;
					} else {
						length = 0;
						printk("ERROR command too long\r\n");
					}
				}
			}
		} else {
			length = 0;
		}
		connected_before = connected;
		k_msleep(10);
	}
	return 0;
}
