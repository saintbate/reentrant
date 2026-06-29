/* BUG: flag is set in ISR, read in main, no volatile, no guard */
#include <stdint.h>

int flag = 0;

void EXTI0_IRQHandler(void) {
    flag = 1;
}

void main_loop(void) {
    while (1) {
        if (flag) {
            flag = 0;
            /* do work */
        }
    }
}
