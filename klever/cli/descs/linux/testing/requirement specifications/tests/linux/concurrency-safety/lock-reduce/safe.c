/*
 * Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
 * Ivannikov Institute for System Programming of the Russian Academy of Sciences
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
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/* Test check the reduction of locks. */
#include <linux/module.h>
#include <linux/mutex.h>
#include <ldv/verifier/nondet.h>
#include <ldv/verifier/thread.h>

static DEFINE_MUTEX(ldv_lock);
static DEFINE_MUTEX(ldv_lock2);
static DEFINE_MUTEX(ldv_lock3);
static int _ldv_global_var;

static int ldv_func(void)
{
	_ldv_global_var = 0;
	mutex_lock(&ldv_lock);
	mutex_lock(&ldv_lock2);
	mutex_lock(&ldv_lock3);

	return 0;
}

static void *ldv_main(void *arg)
{
	mutex_lock(&ldv_lock);
	mutex_lock(&ldv_lock);
	mutex_lock(&ldv_lock2);
	/* (2,1,0) -> (1,1,0) */
	ldv_func();
	/* (0,2,1) -> (1,2,1) */
	/* (1,2,1) -> (1,1,1) */
	ldv_func();
	/* (0,2,2) -> (0,3,3) */
	mutex_unlock(&ldv_lock2);
	mutex_unlock(&ldv_lock2);
	mutex_unlock(&ldv_lock2);
	/* (0,0,3) -> (0,0,1) */
	ldv_func();
	/* (0,1,2) -> (0,1,4) */
	
	return NULL;
}

static int __init ldv_init(void)
{
	pthread_t thread1, thread2;
	pthread_attr_t const *attr = ldv_undef_ptr();
	void *arg1 = ldv_undef_ptr(), *arg2 = ldv_undef_ptr();

	pthread_create(&thread1, attr, &ldv_main, arg1);
	pthread_create(&thread2, attr, &ldv_main, arg2);

	return 0;
}

module_init(ldv_init);
