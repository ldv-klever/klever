/*
 * Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
 * Institute for System Programming of the Russian Academy of Sciences
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * ee the License for the specific language governing permissions and
 * limitations under the License.
 */

#ifndef __VERIFIER_THREAD_H
#define __VERIFIER_THREAD_H

struct ldv_thread {
    int identifier;
    void (*function)(void *);
};

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
