#ifndef __VERIFIER_THREAD_H
#define __VERIFIER_THREAD_H

/* Thread type */
struct ldv_thread;

/* Set of threads */
struct ldv_thread_set
{
    int number;
    struct ldv_thread **threads;
};

/* Create thread */
extern int ldv_thread_create(struct ldv_thread *ldv_thread, void (*function)(void *), void *data);

/* Create N threads */
extern int ldv_thread_create_N(struct ldv_thread_set *ldv_thread_set, void (*function)(void *), void *data);

/* Join thread */
extern int ldv_thread_join(struct ldv_thread *ldv_thread, void (*function)(void *));

/* Join N threads */
extern int ldv_thread_join_N(struct ldv_thread_set *ldv_thread_set, void (*function)(void *));

#endif /* __VERIFIER_THREAD_H */
