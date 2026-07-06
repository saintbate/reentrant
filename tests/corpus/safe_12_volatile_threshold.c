/* SAFE: mirrors safe_03_readonly.c's read-only-in-ISR pattern, but with
   volatile — proves the isr-stale-read Tier 2 rule respects the same
   volatile suppression as isr-shared-var. */
#include <stdint.h>

volatile uint32_t threshold = 100;

void ADC_IRQHandler(void) {
    if (threshold > 50) {
        /* act */
    }
}

void set_threshold(uint32_t v) {
    threshold = v;
}
