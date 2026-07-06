/* SAFE: correctly uses the FromISR variant inside the ISR. xQueueSendFromISR
   is the ISR-safe counterpart of xQueueSend and is not itself flagged. */
#include <stdint.h>

extern int xQueueSendFromISR(void *queue, const void *item, void *woken);

static void *event_queue;

void TIM8_IRQHandler(void) {
    uint32_t event = 1;
    int higher_priority_task_woken = 0;
    xQueueSendFromISR(event_queue, &event, &higher_priority_task_woken);
}
