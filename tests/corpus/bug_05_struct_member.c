/* BUG: a user-defined struct (not a HAL handle) has a member written in ISR
   and read in main.  Tests that suppression only covers HAL handle types,
   not arbitrary structs. */
#include <stdint.h>

typedef struct {
    uint8_t data[16];
    int len;
    int ready;
} MsgBuf;

MsgBuf msg_buf;

void USART1_IRQHandler(void) {
    msg_buf.len = 4;
    msg_buf.ready = 1;
}

void handle_msg(void) {
    if (msg_buf.ready) {
        msg_buf.ready = 0;
    }
}
