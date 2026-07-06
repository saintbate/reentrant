/* BUG: HAL_UART_Transmit is the blocking, polling-mode transmit — calling it
   inside an ISR ties up the interrupt until the whole buffer is sent. */
#include <stdint.h>

extern int HAL_UART_Transmit(void *huart, uint8_t *data, uint16_t size, uint32_t timeout);

void USART3_IRQHandler(void) {
    uint8_t msg[4] = {0, 1, 2, 3};
    HAL_UART_Transmit((void *)0, msg, 4, 100);
}
