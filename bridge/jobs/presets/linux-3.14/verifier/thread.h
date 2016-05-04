#ifndef _LDV_THREAD_H_
#define _LDV_THREAD_H_

/* Create thread */
extern int ldv_thread_create(void *ldv_thread, void (*function)(void *), void *data);

/* Join thread */
extern int ldv_thread_join(void *ldv_thread);

#endif /* _LDV_THREAD_H_ */