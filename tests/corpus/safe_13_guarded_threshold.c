/* SAFE: the non-ISR write to threshold is wrapped in a critical section, so
   the ISR's read can never observe a torn value — isr-stale-read must not
   flag this. */
#include <stdint.h>

extern void __disable_irq(void);
extern void __enable_irq(void);

uint32_t threshold = 100;

void ADC_IRQHandler(void) {
    if (threshold > 50) {
        /* act */
    }
}

void set_threshold(uint32_t v) {
    __disable_irq();
    threshold = v;
    __enable_irq();
}
