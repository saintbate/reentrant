/* BUG: malloc() is not reentrant — calling it inside an ISR risks heap
   corruption if the ISR interrupts another allocation already in progress. */
#include <stdlib.h>

void EXTI3_IRQHandler(void) {
    void *buf = malloc(16);
    (void)buf;
}
