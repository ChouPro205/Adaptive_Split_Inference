/*
 * Week 2 PPK2 idle-current baseline for the PCA10059.
 * D0-D3 stay LOW, every onboard LED stays off, and no workload is run.
 */

#include "markers.h"

#include <stddef.h>

#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/util.h>

#define LED0_NODE DT_ALIAS(led0)
#define LED1_NODE DT_ALIAS(led1)
#define LED2_NODE DT_ALIAS(led2)
#define LED3_NODE DT_ALIAS(led3)

BUILD_ASSERT(DT_NODE_HAS_STATUS(LED0_NODE, okay),
	     "The board must provide an enabled led0 alias");
BUILD_ASSERT(DT_NODE_HAS_STATUS(LED1_NODE, okay),
	     "The board must provide an enabled led1 alias");
BUILD_ASSERT(DT_NODE_HAS_STATUS(LED2_NODE, okay),
	     "The board must provide an enabled led2 alias");
BUILD_ASSERT(DT_NODE_HAS_STATUS(LED3_NODE, okay),
	     "The board must provide an enabled led3 alias");

static const struct gpio_dt_spec onboard_leds[] = {
	GPIO_DT_SPEC_GET(LED0_NODE, gpios),
	GPIO_DT_SPEC_GET(LED1_NODE, gpios),
	GPIO_DT_SPEC_GET(LED2_NODE, gpios),
	GPIO_DT_SPEC_GET(LED3_NODE, gpios),
};

static void turn_off_onboard_leds(void)
{
	for (size_t index = 0U; index < ARRAY_SIZE(onboard_leds); ++index) {
		if (gpio_is_ready_dt(&onboard_leds[index])) {
			(void)gpio_pin_configure_dt(&onboard_leds[index],
						GPIO_OUTPUT_INACTIVE);
		}
	}
}

int main(void)
{
	/* markers_init() drives Active D0-D3 (P0.13/15/17/20) LOW. */
	(void)markers_init();
	turn_off_onboard_leds();

	/* Block forever so Zephyr's idle thread can place the CPU in idle. */
	k_sleep(K_FOREVER);

	return 0;
}
