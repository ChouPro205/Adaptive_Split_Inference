/* Debug acceptance protocol only. I1/I2 and radio are separate future work. */
#include "quantization.h"
#include "week4_head.h"
#include "week4_inputs.h"
#include "week4_protocol.h"
#include "week5_build.h"
#include "markers.h"
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

BUILD_ASSERT(DT_NODE_HAS_COMPAT(DT_CHOSEN(zephyr_console), zephyr_cdc_acm_uart),
             "Week 5 requires USB CDC ACM");
BUILD_ASSERT(WEEK4_BUFFER_COUNT == 5760U && WEEK4_SAMPLE_COUNT == 20U && WEEK4_SPLIT_COUNT == 11U,
             "Authenticated Week 5 mapping limits differ");
static const struct device *const console_device = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));
static int8_t quantized[5760];
static uint8_t scale_le[64 * 2];

static void paced_newline(void)
{
    printk("\r\n");
    k_msleep(5);
}

static void process(unsigned sample, unsigned split)
{
    struct week4_result result;
    printk("BEGIN %u %s %u RUN\r\n", sample, week4_sample_ids[sample], split);
    marker_on(MARKER_HEAD);
    int status = week4_run_head(split, week4_inputs[sample], &result);
    marker_off(MARKER_HEAD);
    if (status) { printk("ERROR head\r\n"); return; }
    unsigned channels = result.shape.dims[1];
    unsigned length = result.shape.rank == 3U ? result.shape.dims[2] : 1U;
    if (channels > 64U || result.shape.count > 5760U || channels * length != result.shape.count) {
        printk("ERROR mapping bounds\r\n"); return;
    }
    status = week5_quantize(result.values, result.shape.count, 1, channels, length,
                           quantized, sizeof(quantized), scale_le, sizeof(scale_le));
    if (status) { printk("ERROR quantization %d\r\n", status); return; }
    /* No subsequent head call until all borrowed activation words are emitted. */
    printk("HEAD %u %s %u FP32 %s %u", sample, week4_sample_ids[sample], split,
           result.shape.rank == 3U ? "NCL" : "NC", result.shape.rank);
    for (unsigned i = 0; i < result.shape.rank; ++i) { printk(" %u", result.shape.dims[i]); }
    printk(" %u\r\n", result.shape.count);
    for (unsigned i = 0; i < result.shape.count; ++i) {
        uint32_t bits;
        memcpy(&bits, &result.values[i], sizeof(bits));
        printk("%08x", bits);
        if (i % 16U == 15U || i + 1U == result.shape.count) { paced_newline(); }
        else { printk(" "); }
    }
    printk("ENDHEAD %u %u\r\n", sample, split);
    printk("Q %u %u NCL 1 %u %u %u\r\n", sample, split, channels, length, result.shape.count);
    for (unsigned i = 0; i < result.shape.count; ++i) {
        printk("%02x", (unsigned)(uint8_t)quantized[i]);
        if (i % 32U == 31U || i + 1U == result.shape.count) { paced_newline(); }
        else { printk(" "); }
    }
    printk("ENDQ %u %u\r\n", sample, split);
    printk("SCALE %u %u FP16LE 1 %u %u\r\n", sample, split, channels, channels);
    for (unsigned c = 0; c < channels; ++c) {
        unsigned bits = scale_le[2U * c] | ((unsigned)scale_le[2U * c + 1U] << 8);
        printk("%04x", bits);
        if (c % 16U == 15U || c + 1U == channels) { paced_newline(); }
        else { printk(" "); }
    }
    printk("ENDSCALE %u %u\r\nDONE %u %u RUN\r\n", sample, split, sample, split);
}

int main(void)
{
    char line[48];
    unsigned length = 0;
    bool discard = false, connected_before = false;
    if (!device_is_ready(console_device) || markers_init() != 0) { return -1; }
    struct uart_config config = {
        .baudrate = 115200, .parity = UART_CFG_PARITY_NONE, .stop_bits = UART_CFG_STOP_BITS_1,
        .data_bits = UART_CFG_DATA_BITS_8, .flow_ctrl = UART_CFG_FLOW_CTRL_RTS_CTS,
    };
    if (uart_configure(console_device, &config) != 0) { return -1; }
    /* Retain accepted TX backpressure, USB OUT arming and worker pacing. */
    uart_irq_rx_enable(console_device);
    while (true) {
        uint32_t dtr = 0;
        bool connected = uart_line_ctrl_get(console_device, UART_LINE_CTRL_DTR, &dtr) == 0 && dtr;
        if (connected && !connected_before) {
            k_msleep(100);
            printk("READY WEEK5 V1 fw=%s r3=%s model=%s quant=%s samples=20 splits=11\r\n",
                   WEEK5_FIRMWARE_ID, WEEK4_MANIFEST_SHA256, WEEK5_MODEL_ANCHOR, WEEK5_QUANT_ANCHOR);
            printk("COMMAND RUN n s (n=0..19 s=0..10)\r\n");
            length = 0; discard = false;
        }
        if (connected) {
            unsigned char byte;
            while (uart_poll_in(console_device, &byte) == 0) {
                if (byte == '\n') {
                    line[length] = '\0';
                    struct week4_command command;
                    if (!discard && week4_parse_command(line, &command) == 0 && command.type == WEEK4_RUN) {
                        process(command.sample, command.split);
                    } else { printk("ERROR expected RUN n s (n=0..19 s=0..10)\r\n"); }
                    length = 0; discard = false;
                } else if (byte != '\r' && !discard) {
                    if (byte == '\0' || length + 1U >= sizeof(line)) { discard = true; }
                    else { line[length++] = (char)byte; }
                }
            }
        } else { length = 0; discard = false; }
        connected_before = connected;
        k_msleep(10);
    }
    return 0;
}
