/* SAFE: volatile keyword present — visibility addressed */
#include <stdint.h>

volatile int flag = 0;

void EXTI0_IRQHandler(void) {
    flag = 1;
}

void main_loop(void) {
    while (1) {
        if (flag) {
            flag = 0;
        }
    }
}
