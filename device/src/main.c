/*
 * Adaptive Split Inference - SV1 Week 1 demo
 * Target: Nordic nRF52840 Dongle PCA10059 (nrf52840dongle/nrf52840)
 */

#include <stdbool.h>
#include <stdint.h>

#include <cmsis_core.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/irq.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#define LED0_NODE DT_ALIAS(led0)

#define HEARTBEAT_PERIOD_MS       1000
#define HEARTBEAT_TOGGLE_MS       (HEARTBEAT_PERIOD_MS / 2)
#define CONSOLE_POLL_INTERVAL_MS  20
#define STATUS_PERIOD_MS          5000
#define DTR_SETTLE_TIME_MS        100
#define WARMUP_RUN_COUNT          20U
#define MEASUREMENT_RUN_COUNT     20U
#define BENCHMARK_ITERATION_COUNT 10000U

BUILD_ASSERT(DT_NODE_HAS_STATUS(LED0_NODE, okay),
	     "The board must provide an enabled led0 alias");
BUILD_ASSERT(DT_NODE_HAS_COMPAT(DT_CHOSEN(zephyr_console), zephyr_cdc_acm_uart),
	     "The console must be a USB CDC ACM UART");

typedef void (*benchmark_function_t)(uint32_t iteration_count);

static const struct gpio_dt_spec status_led = GPIO_DT_SPEC_GET(LED0_NODE, gpios);
static const struct device *const console_device =
	DEVICE_DT_GET(DT_CHOSEN(zephyr_console));
static volatile uint32_t measured_cycles[MEASUREMENT_RUN_COUNT];
static volatile uint32_t benchmark_sink;
static uint32_t last_min_cycles;
static uint32_t last_max_cycles;
static uint64_t last_average_milli_cycles;
static uint64_t last_deviation_milli_percent;
static bool last_result_passed;
static bool benchmark_result_available;

static inline uint32_t dwt_cycle_count_get(void)
{
	__asm__ volatile("" ::: "memory");
	uint32_t cycle_count = DWT->CYCCNT;
	__asm__ volatile("" ::: "memory");

	return cycle_count;
}

static bool dwt_cycle_counter_init(void)
{
	CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
	DWT->CYCCNT = 0U;
	DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
	__DSB();
	__ISB();

	for (uint32_t nop_count = 0U; nop_count < 8U; ++nop_count) {
		__asm__ volatile("nop" ::: "memory");
	}

	return ((DWT->CTRL & DWT_CTRL_NOCYCCNT_Msk) == 0U) &&
	       (DWT->CYCCNT != 0U);
}

static void empty_loop_benchmark(uint32_t iteration_count)
{
	volatile uint32_t iteration;

	for (iteration = 0U; iteration < iteration_count; ++iteration) {
		__asm__ volatile("nop" ::: "memory");
	}

	benchmark_sink = iteration;
}

static uint32_t measure_cycles(benchmark_function_t benchmark_function)
{
	unsigned int irq_key = irq_lock();
	uint32_t start_cycles = dwt_cycle_count_get();

	benchmark_function(BENCHMARK_ITERATION_COUNT);
	uint32_t end_cycles = dwt_cycle_count_get();
	irq_unlock(irq_key);

	return end_cycles - start_cycles;
}

static void print_fixed_point(uint64_t milli_value, const char *suffix)
{
	printk("%llu.%03llu%s", (unsigned long long)(milli_value / 1000U),
	       (unsigned long long)(milli_value % 1000U), suffix);
}

static void run_and_report_benchmark(void)
{
	benchmark_function_t benchmark_function = empty_loop_benchmark;
	uint64_t cycle_sum = 0U;
	uint32_t min_cycles = UINT32_MAX;
	uint32_t max_cycles = 0U;

	printk("DWT benchmark: START\r\n");
	printk("Warm-up runs: %u; measured runs: %u; iterations/run: %u\r\n",
	       WARMUP_RUN_COUNT, MEASUREMENT_RUN_COUNT,
	       BENCHMARK_ITERATION_COUNT);

	for (uint32_t run = 0U; run < WARMUP_RUN_COUNT; ++run) {
		(void)measure_cycles(benchmark_function);
	}

	for (uint32_t run = 0U; run < MEASUREMENT_RUN_COUNT; ++run) {
		uint32_t elapsed_cycles = measure_cycles(benchmark_function);

		measured_cycles[run] = elapsed_cycles;
		cycle_sum += elapsed_cycles;
		if (elapsed_cycles < min_cycles) {
			min_cycles = elapsed_cycles;
		}
		if (elapsed_cycles > max_cycles) {
			max_cycles = elapsed_cycles;
		}
		printk("Run %02u: %u cycles\r\n", run + 1U, elapsed_cycles);
	}

	last_min_cycles = min_cycles;
	last_max_cycles = max_cycles;
	last_average_milli_cycles =
		(cycle_sum * 1000U) / MEASUREMENT_RUN_COUNT;
	last_deviation_milli_percent =
		((uint64_t)(max_cycles - min_cycles) *
		 MEASUREMENT_RUN_COUNT * 100000U) /
		cycle_sum;
	last_result_passed = last_deviation_milli_percent < 1000U;
	benchmark_result_available = true;

	printk("Min: %u cycles\r\n", last_min_cycles);
	printk("Max: %u cycles\r\n", last_max_cycles);
	printk("Average: ");
	print_fixed_point(last_average_milli_cycles, " cycles\r\n");
	printk("Deviation: ");
	print_fixed_point(last_deviation_milli_percent, "%%\r\n");
	printk("RESULT: %s\r\n", last_result_passed ? "PASS" : "FAIL");
}

static void print_banner(bool led_operational, bool dwt_operational)
{
	uint32_t cpu_freq_hz = SystemCoreClock;

	printk("\r\n========================================\r\n");
	printk("ADAPTIVE SPLIT INFERENCE - SV1 WEEK 1\r\n");
	printk("Board: nRF52840 Dongle PCA10059\r\n");
	printk("CPU: %u MHz\r\n", cpu_freq_hz / 1000000U);
	printk("USB CDC: READY\r\n");
	printk("LED heartbeat: %s\r\n", led_operational ? "RUNNING" : "ERROR");
	if (!led_operational) {
		printk("ERROR: led0 GPIO initialization or toggle failed\r\n");
	}
	if (!dwt_operational) {
		printk("DWT benchmark: ERROR - CYCCNT unavailable\r\n");
		printk("RESULT: FAIL\r\n");
	}
}

static void print_periodic_status(bool led_operational)
{
	printk("STATUS: USB CDC CONNECTED | LED heartbeat: %s",
	       led_operational ? "RUNNING" : "ERROR");
	if (benchmark_result_available) {
		printk(" | last deviation: ");
		print_fixed_point(last_deviation_milli_percent, "%%");
		printk(" | RESULT: %s", last_result_passed ? "PASS" : "FAIL");
	}
	printk("\r\n");
}

static void update_heartbeat(bool *led_operational, int64_t *next_toggle_ms)
{
	int64_t now_ms = k_uptime_get();

	if (*led_operational && now_ms >= *next_toggle_ms) {
		int result = gpio_pin_toggle_dt(&status_led);

		if (result != 0) {
			*led_operational = false;
		}
		*next_toggle_ms = now_ms + HEARTBEAT_TOGGLE_MS;
	}
}

int main(void)
{
	bool led_operational = gpio_is_ready_dt(&status_led);
	bool terminal_was_connected = false;
	bool dwt_operational;
	int64_t next_toggle_ms = k_uptime_get() + HEARTBEAT_TOGGLE_MS;
	int64_t next_status_ms = 0;

	if (led_operational) {
		led_operational =
			gpio_pin_configure_dt(&status_led, GPIO_OUTPUT_INACTIVE) == 0;
	}

	dwt_operational = dwt_cycle_counter_init();

	if (!device_is_ready(console_device)) {
		while (true) {
			update_heartbeat(&led_operational, &next_toggle_ms);
			k_msleep(CONSOLE_POLL_INTERVAL_MS);
		}
	}

	while (true) {
		uint32_t dtr = 0U;
		bool terminal_connected =
			uart_line_ctrl_get(console_device, UART_LINE_CTRL_DTR, &dtr) == 0 &&
			dtr != 0U;

		update_heartbeat(&led_operational, &next_toggle_ms);

		if (terminal_connected && !terminal_was_connected) {
			k_msleep(DTR_SETTLE_TIME_MS);
			update_heartbeat(&led_operational, &next_toggle_ms);
			print_banner(led_operational, dwt_operational);
			if (dwt_operational) {
				run_and_report_benchmark();
			}
			next_status_ms = k_uptime_get() + STATUS_PERIOD_MS;
		} else if (terminal_connected && k_uptime_get() >= next_status_ms) {
			print_periodic_status(led_operational);
			next_status_ms = k_uptime_get() + STATUS_PERIOD_MS;
		}

		terminal_was_connected = terminal_connected;
		k_msleep(CONSOLE_POLL_INTERVAL_MS);
	}

	return 0;
}
