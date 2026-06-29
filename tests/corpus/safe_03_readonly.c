/* SAFE: variable is only READ in ISR, never written — no race possible */
#include <stdint.h>

uint32_t threshold = 100;

void ADC_IRQHandler(void) {
    /* read-only use inside ISR — no writer in ISR context */
    if (threshold > 50) {
        /* act */
    }
}

void set_threshold(uint32_t v) {
    threshold = v;
}
