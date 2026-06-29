/* BUG: this file's own static int counter IS written by an ISR. */
static int counter = 0;

void SPI2_IRQHandler(void) {
    counter = 0;
}

void reset_queue(void) {
    counter = 0;
}
