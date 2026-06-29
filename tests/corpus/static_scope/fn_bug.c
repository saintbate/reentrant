/* BUG: this file's static int sensor is non-volatile.
   The ISR writes it and main reads it without a guard.
   Must still be flagged even when fn_safe.c's volatile version is present. */
static int sensor = 0;

void ADC_IRQHandler(void) {
    sensor = 42;
}

void read_sensor_buggy(void) {
    (void)sensor;
}
