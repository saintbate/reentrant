/* BUG: variable touched via a helper called from the ISR — tests transitive
   ISR-context reachability, not just direct access in the handler body. */
#include <stdint.h>

static uint16_t adc_value = 0;

static void store_adc(uint16_t v) {
    adc_value = v;
}

void ADC_IRQHandler(void) {
    store_adc(1234);
}

uint16_t read_adc(void) {
    return adc_value;
}
