/* SAFE: mirrors FreeRTOS's own idiom for kernel-internal globals, e.g.
   pxCurrentTCB / pxDelayedTaskList in tasks.c: `Type * volatile name` —
   volatile qualifies the POINTER itself, not the pointee. tree-sitter
   parses this qualifier as a child of the pointer_declarator, not a
   sibling of the base type, so it needs its own check. Found as a
   real-world false positive via tests/measure_fp.py against actual
   FreeRTOS source bundled in several real firmware repos. */
typedef struct list_item { int value; } List_t;

static List_t * volatile pxDelayedTaskList;

void TIM2_IRQHandler(void) {
    pxDelayedTaskList = 0;
}

List_t *read_delayed_list(void) {
    return pxDelayedTaskList;
}
