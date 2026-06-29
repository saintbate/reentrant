/* SAFE: FreeRTOS taskENTER_CRITICAL / taskEXIT_CRITICAL guard */
#include <stdint.h>

extern void taskENTER_CRITICAL(void);
extern void taskEXIT_CRITICAL(void);

static int shared_val = 0;

void TIM3_IRQHandler(void) {
    shared_val++;
}

int read_shared(void) {
    taskENTER_CRITICAL();
    int v = shared_val;
    taskEXIT_CRITICAL();
    return v;
}
