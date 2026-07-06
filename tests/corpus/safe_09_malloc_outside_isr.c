/* SAFE: malloc() is only called from main-loop code, never from an ISR.
   The ISR itself does something unrelated to allocation. */
#include <stdint.h>
#include <stdlib.h>

static volatile uint8_t data_ready = 0;

void EXTI4_IRQHandler(void) {
    data_ready = 1;
}

void process_data(void) {
    if (data_ready) {
        void *buf = malloc(32);
        (void)buf;
    }
}
