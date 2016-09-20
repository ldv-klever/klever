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
