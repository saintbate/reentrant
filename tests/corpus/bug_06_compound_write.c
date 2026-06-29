/* BUG: compound write (|=) to a flag word in both ISR and main without a
   guard.  The ISR sets bits; main clears them — both paths are writes.
   On Cortex-M the read-modify-write is not atomic; ISR can clobber main's
   in-flight update. */
#include <stdint.h>

#define FLAG_UART_RX  (1u << 0)
#define FLAG_TIMER    (1u << 1)

uint32_t event_mask = 0;

void USART2_IRQHandler(void) {
    event_mask |= FLAG_UART_RX;
}

void TIM6_DAC_IRQHandler(void) {
    event_mask |= FLAG_TIMER;
}

void process_events(void) {
    if (event_mask & FLAG_UART_RX) {
        event_mask &= ~FLAG_UART_RX;
    }
    if (event_mask & FLAG_TIMER) {
        event_mask &= ~FLAG_TIMER;
    }
}
