/* BUG: xQueueSend is not ISR-safe — it may attempt to block/yield, which is
   undefined behaviour in interrupt context. xQueueSendFromISR exists for
   exactly this reason. */
#include <stdint.h>

extern int xQueueSend(void *queue, const void *item, uint32_t ticks);

static void *event_queue;

void TIM7_IRQHandler(void) {
    uint32_t event = 1;
    xQueueSend(event_queue, &event, 0);
}
