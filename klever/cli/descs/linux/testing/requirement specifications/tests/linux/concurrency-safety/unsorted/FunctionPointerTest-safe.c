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

/*
 * The test should check processing of function pointers with different
 * declarations.
 */
#include <linux/module.h>
#include <linux/mutex.h>
#include <ldv/verifier/nondet.h>
#include <ldv/verifier/thread.h>

static DEFINE_MUTEX(ldv_lock);
static int _ldv_global_var = 0;

static struct ldv_struct {
	int (*field1)(void);
	int (*field2)(void);
	int (*field3)(int d);
} *_ldv_var;

static int ldv_hook(void)
{
	int b = 0;

	mutex_lock(&ldv_lock);
	_ldv_global_var = b++;
	mutex_unlock(&ldv_lock);

	return b;
}

static int ldv_hook1(int arg)
{
	int b = arg + 1;

	mutex_lock(&ldv_lock);
	_ldv_global_var = b++;
	mutex_unlock(&ldv_lock);

	return b;
}

static int ldv_hook2(int arg)
{
	/* This function is not called! Please, do not delete it: CPAchecker
	 * should understand it is not called. */
	int b = arg + 1;

	_ldv_global_var = b++;

	return b;
}

static int ldv_func(int arg)
{
	int t = arg;

	_ldv_var->field1();
	_ldv_var->field2();
	_ldv_var->field3(t);

	return 0;
}

static void *ldv_locker(void *arg)
{
	mutex_lock(&ldv_lock);
	_ldv_global_var = 4;
	mutex_unlock(&ldv_lock);

	return NULL;
}

static int __init ldv_init(void)
{
	pthread_t thread;
	pthread_attr_t const *attr = ldv_undef_ptr();
	void *arg1 = ldv_undef_ptr();
	int arg2 = ldv_undef_int();
	_ldv_var->field1 = &ldv_hook;
	_ldv_var->field2 = &ldv_hook;
	_ldv_var->field3 = &ldv_hook1;

	pthread_create(&thread, attr, &ldv_locker, arg1);
	ldv_func(arg2);

	return 0;
}

module_init(ldv_init);
