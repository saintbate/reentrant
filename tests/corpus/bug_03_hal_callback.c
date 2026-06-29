/* BUG: shared via HAL callback (not _IRQHandler) — the key case the brief
   specifically calls out.  rx_ready set in callback, consumed in main. */
#include <stdint.h>

static uint8_t rx_buf[64];
static int rx_ready = 0;

void HAL_UART_RxCpltCallback(void *huart) {
    rx_ready = 1;
}

void process_uart(void) {
    if (rx_ready) {
        rx_ready = 0;
        /* handle rx_buf */
    }
}
