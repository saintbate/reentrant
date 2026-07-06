/* SAFE: mirrors the CMSIS-RTOS os*() wrapper pattern (cmsis_os.c) — a
   runtime check picks the ISR-safe variant in interrupt context and the
   normal variant otherwise. Both calls appearing in the same function is
   deliberate, not a bug: the isr-blocking-call rule must not flag the
   xSemaphoreGive() call just because this wrapper is reachable from an ISR. */
#include <stdint.h>

extern int inHandlerMode(void);
extern int xSemaphoreGive(void *sem);
extern int xSemaphoreGiveFromISR(void *sem, int *woken);

static void *my_semaphore;

static void osSemaphoreRelease_like(void) {
    if (inHandlerMode()) {
        int woken = 0;
        xSemaphoreGiveFromISR(my_semaphore, &woken);
    } else {
        xSemaphoreGive(my_semaphore);
    }
}

void DMA1_Channel1_IRQHandler(void) {
    osSemaphoreRelease_like();
}
