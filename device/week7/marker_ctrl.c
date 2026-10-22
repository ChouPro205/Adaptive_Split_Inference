/* See marker_ctrl.h. */
#include "marker_ctrl.h"

#include <errno.h>

#include <hal/nrf_gpio.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/sys/util.h>

#define GPIO0_NODE DT_NODELABEL(gpio0)

/* P0.19/21/23/25 are tied to SW2, P0.06/P0.08/P0.12 and P1.09 drive LEDs, P0.09/P0.10 are NFC:
 * none of them may carry a marker (user guide 4440_052, figure 3 and footnote 1 of 6.6). */
BUILD_ASSERT(MARKER_CTRL_PIN == 22U, "decision W7-D4: D4 = P0.22");

static const struct device *const port = DEVICE_DT_GET(GPIO0_NODE);

int marker_ctrl_init(void)
{
	NRF_P0->OUTCLR = BIT(MARKER_CTRL_PIN);
	if (!device_is_ready(port)) {
		return -ENODEV;
	}
	return gpio_pin_configure(port, MARKER_CTRL_PIN, GPIO_OUTPUT_INACTIVE);
}

void marker_ctrl_on(void)
{
	NRF_P0->OUTSET = BIT(MARKER_CTRL_PIN);
}

void marker_ctrl_off(void)
{
	NRF_P0->OUTCLR = BIT(MARKER_CTRL_PIN);
}
