/* BUG: 32-bit counter incremented in TIM ISR, read in main without guard.
   On Cortex-M0 32-bit reads are not atomic — 2 half-word loads can tear. */
#include <stdint.h>

uint32_t tick_count = 0;

void TIM2_IRQHandler(void) {
    tick_count++;
}

uint32_t get_ticks(void) {
    return tick_count;
}
