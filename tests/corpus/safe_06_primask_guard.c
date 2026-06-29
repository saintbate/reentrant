/* SAFE: ARM PRIMASK save/disable/restore critical section.
   __get_PRIMASK saves state, __disable_irq enters, __set_PRIMASK exits.
   This is the canonical bare-metal pattern for nested-interrupt-safe sections. */
#include <stdint.h>

extern void     __disable_irq(void);
extern uint32_t __get_PRIMASK(void);
extern void     __set_PRIMASK(uint32_t);

static uint32_t event_flags = 0;

void EXTI1_IRQHandler(void) {
    event_flags |= 0x01u;
}

uint32_t consume_events(void) {
    uint32_t primask = __get_PRIMASK();
    __disable_irq();
    uint32_t flags = event_flags;
    event_flags    = 0;
    __set_PRIMASK(primask);
    return flags;
}
