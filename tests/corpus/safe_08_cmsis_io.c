/* SAFE: CMSIS __IO type alias is treated as volatile — must not be flagged.
   __IO expands to volatile in CMSIS headers; our symbol table recognises it
   via the _CMSIS_VOLATILE_TYPES regex. */
#include <stdint.h>

/* Minimal CMSIS __IO definition (normally in core_cm*.h) */
#define __IO volatile

__IO uint32_t dma_complete = 0;

void DMA1_Stream0_IRQHandler(void) {
    dma_complete = 1;
}

void wait_for_dma(void) {
    while (!dma_complete) {}
    dma_complete = 0;
}
