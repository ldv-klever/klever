#include <verifier/thread.h>

/* Thread type */
struct ldv_thread {
    int identifier;
    void (*function)(void *);
};

/* Create thread */
int ldv_thread_create(struct ldv_thread *ldv_thread, void (*function)(void *), void *data)
{
    if (function)
        (*function)(data);
    return 0;
}

/* Create n threads */
int ldv_thread_create_N(struct ldv_thread_set *ldv_thread_set, void (*function)(void *), void *data)
{
    int i;

    if (function) {
        for (i = 0; i < ldv_thread_set->number; i++) {
           (*function)(data);
        }
    }
    return 0;
}

/* Join thread */
int ldv_thread_join(struct ldv_thread *ldv_thread, void (*function)(void *))
{
    return 0;
}

/* Join n threads */
int ldv_thread_join_N(struct ldv_thread_set *ldv_thread_set, void (*function)(void *))
{
    return 0;
}
