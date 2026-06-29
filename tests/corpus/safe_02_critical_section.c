/* SAFE: non-ISR accesses consistently wrapped in __disable_irq/__enable_irq */
#include <stdint.h>

extern void __disable_irq(void);
extern void __enable_irq(void);

uint32_t tick_count = 0;

void TIM2_IRQHandler(void) {
    tick_count++;
}

uint32_t get_ticks(void) {
    __disable_irq();
    uint32_t t = tick_count;
    __enable_irq();
    return t;
}
