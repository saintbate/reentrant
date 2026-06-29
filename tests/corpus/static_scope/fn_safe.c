/* This file has static volatile int sensor — safe on its own.
   Its volatile qualifier must NOT mask the bug in fn_bug.c. */
static volatile int sensor = 0;

void read_sensor_safe(void) {
    (void)sensor;
}
