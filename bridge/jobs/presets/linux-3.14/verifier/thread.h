#ifndef __VERIFIER_THREAD_H
#define __VERIFIER_THREAD_H

/* Thread type */
struct ldv_thread;

/* Create thread */
extern int ldv_thread_create(void *ldv_thread, void (*function)(void *), void *data);

/* Join thread */
extern int ldv_thread_join(void *ldv_thread);

#endif /* __VERIFIER_THREAD_H */