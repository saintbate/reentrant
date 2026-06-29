/* This file has its own static int counter — never touched by any ISR.
   It must NOT appear in findings when analyzed alongside fp_bug.c. */
static int counter = 0;

void dequeue(void) {
    counter--;
}
