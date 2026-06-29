/* SAFE: variable is only ever accessed inside ISR context — no non-ISR access */
#include <stdint.h>

static uint32_t isr_local_counter = 0;

void EXTI1_IRQHandler(void) {
    isr_local_counter++;
    if (isr_local_counter > 1000) {
        isr_local_counter = 0;
    }
}
