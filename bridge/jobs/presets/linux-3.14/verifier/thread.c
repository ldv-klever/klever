#include <verifier/thread.h>

/* Create thread */
int ldv_thread_create(void *ldv_thread, void (*function)(void *), void *data) {
    if (function)
        (*function)(data);
    return 0;
}

/* Join thread */
int ldv_thread_join(void *ldv_thread) {
    return 0;
}