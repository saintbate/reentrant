/* SAFE: FreeRTOS portDISABLE_INTERRUPTS / portENABLE_INTERRUPTS guard.
   Distinct from taskENTER_CRITICAL — used in ISR-safe task code when the
   FreeRTOS scheduler is not yet running or in bare-metal FreeRTOS ports. */
#include <stdint.h>

extern void portDISABLE_INTERRUPTS(void);
extern void portENABLE_INTERRUPTS(void);

static uint16_t sample_buf[8];
static int      sample_count = 0;

void ADC_IRQHandler(void) {
    sample_buf[sample_count % 8] = 42;
    sample_count++;
}

int read_sample_count(void) {
    portDISABLE_INTERRUPTS();
    int n = sample_count;
    portENABLE_INTERRUPTS();
    return n;
}
