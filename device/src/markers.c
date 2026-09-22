/*
 * GPIO timing markers for Week 2.
 *
 * All marker signals are on GPIO Port 0. Direct OUTSET/OUTCLR writes make a
 * marker edge a single peripheral-register write, as required for timing
 * measurements. A static kernel timer keeps the self-test cadence independent
 * of console traffic; printing remains in main-thread context.
 */

#include "markers.h"

#include <errno.h>
#include <stdint.h>

#include <hal/nrf_gpio.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/util.h>

#define GPIO0_NODE              DT_NODELABEL(gpio0)
#define MARKER_HIGH_TIME_MS     500
#define MARKER_HEAD_PIN         13U
#define MARKER_PROTECTION_PIN   15U
#define MARKER_TX_PIN           17U
#define MARKER_WAIT_PIN         20U
#define MARKER_ALL_MASK         (BIT(MARKER_HEAD_PIN) | \
				 BIT(MARKER_PROTECTION_PIN) | \
				 BIT(MARKER_TX_PIN) | \
				 BIT(MARKER_WAIT_PIN))

BUILD_ASSERT(DT_NODE_HAS_STATUS(GPIO0_NODE, okay),
	     "GPIO Port 0 must be enabled for timing markers");

struct marker_description {
	gpio_pin_t pin;
	uint32_t mask;
	const char *name;
};

static const struct device *const marker_port = DEVICE_DT_GET(GPIO0_NODE);
static const struct marker_description marker_descriptions[MARKER_COUNT] = {
	[MARKER_HEAD] = {
		.pin = MARKER_HEAD_PIN,
		.mask = BIT(MARKER_HEAD_PIN),
		.name = "HEAD",
	},
	[MARKER_PROTECTION] = {
		.pin = MARKER_PROTECTION_PIN,
		.mask = BIT(MARKER_PROTECTION_PIN),
		.name = "PROTECTION",
	},
	[MARKER_TX] = {
		.pin = MARKER_TX_PIN,
		.mask = BIT(MARKER_TX_PIN),
		.name = "TX",
	},
	[MARKER_WAIT] = {
		.pin = MARKER_WAIT_PIN,
		.mask = BIT(MARKER_WAIT_PIN),
		.name = "WAIT",
	},
};

static atomic_t active_marker = ATOMIC_INIT(MARKER_HEAD);
static atomic_t transition_count;
static atomic_val_t last_observed_transition;
static bool markers_initialized;
static bool self_test_running;

static bool marker_is_valid(enum marker_id marker)
{
	return (unsigned int)marker < MARKER_COUNT;
}

static void markers_all_low(void)
{
	NRF_P0->OUTCLR = MARKER_ALL_MASK;
}

static void marker_self_test_expiry(struct k_timer *timer)
{
	enum marker_id current = (enum marker_id)atomic_get(&active_marker);
	enum marker_id next = (enum marker_id)((current + 1) % MARKER_COUNT);

	ARG_UNUSED(timer);
	marker_off(current);
	atomic_set(&active_marker, next);
	marker_on(next);
	atomic_inc(&transition_count);
}

K_TIMER_DEFINE(marker_self_test_timer, marker_self_test_expiry, NULL);

int markers_init(void)
{
	k_timer_stop(&marker_self_test_timer);
	self_test_running = false;
	markers_initialized = false;
	markers_all_low();

	if (!device_is_ready(marker_port)) {
		return -ENODEV;
	}

	for (enum marker_id marker = MARKER_HEAD;
	     marker < MARKER_COUNT;
	     marker = (enum marker_id)(marker + 1)) {
		int result = gpio_pin_configure(marker_port,
					marker_descriptions[marker].pin,
					GPIO_OUTPUT_INACTIVE);

		if (result != 0) {
			return result;
		}
	}

	markers_initialized = true;

	return 0;
}

void marker_on(enum marker_id marker)
{
	if (marker_is_valid(marker)) {
		NRF_P0->OUTSET = marker_descriptions[marker].mask;
	}
}

void marker_off(enum marker_id marker)
{
	if (marker_is_valid(marker)) {
		NRF_P0->OUTCLR = marker_descriptions[marker].mask;
	}
}

void markers_self_test_start(void)
{
	if (!markers_initialized) {
		return;
	}

	atomic_set(&active_marker, MARKER_HEAD);
	atomic_set(&transition_count, 0);
	last_observed_transition = 0;
	markers_all_low();
	marker_on(MARKER_HEAD);
	self_test_running = true;
	k_timer_start(&marker_self_test_timer, K_MSEC(MARKER_HIGH_TIME_MS),
		      K_MSEC(MARKER_HIGH_TIME_MS));
}

void markers_self_test_update(bool log_enabled)
{
	atomic_val_t observed_transition;
	enum marker_id marker;

	if (!self_test_running) {
		return;
	}

	observed_transition = atomic_get(&transition_count);
	if (observed_transition == last_observed_transition) {
		return;
	}

	last_observed_transition = observed_transition;
	if (log_enabled) {
		marker = (enum marker_id)atomic_get(&active_marker);
		printk("GPIO marker self-test: %s ON (P0.%u)\r\n",
		       marker_descriptions[marker].name,
		       (unsigned int)marker_descriptions[marker].pin);
	}
}

const char *marker_name(enum marker_id marker)
{
	return marker_is_valid(marker) ? marker_descriptions[marker].name : "INVALID";
}

enum marker_id markers_self_test_active(void)
{
	return (enum marker_id)atomic_get(&active_marker);
}
