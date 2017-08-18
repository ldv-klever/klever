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

typedef unsigned long int pthread_t;

union pthread_attr_t
{
   char __size[56];
   long int __align;
};

typedef union pthread_attr_t pthread_attr_t;

/* Create a thread according to the pthread library interface.
 */
int pthread_create(pthread_t *thread, pthread_attr_t const *attr, void *(*start_routine)(void *), void *arg);

/* Join a thread according to the pthread library interface.
 */
int pthread_join(pthread_t thread, void **value_ptr );

/* Create N threads. This is an artificial function accepted by specific verifiers.
 */
int pthread_create_N(pthread_t **thread, pthread_attr_t const *attr, void *(*function)(void *), void *data);

/* Join N threads. This is an artificial function accepted by specific verifiers.
 */
int pthread_join_N(pthread_t **thread, void (*function)(void *));


#endif /* __VERIFIER_THREAD_H */
