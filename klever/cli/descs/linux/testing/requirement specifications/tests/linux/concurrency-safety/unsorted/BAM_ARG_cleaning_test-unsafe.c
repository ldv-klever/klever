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

/* The test checks the work of cleanin BAM caches. */
#include <linux/module.h>
#include <linux/mutex.h>
#include <verifier/nondet.h>
#include <verifier/thread.h>

static DEFINE_MUTEX(ldv_lock);
static int _ldv_global_var;
static int _ldv_global_var2;

static void ldv_func3(int a) 
{
	/* Uninportant function. */
	int b = 0;

	b++;
	if (a > b)
		b++;
}

static void ldv_func4(int a) 
{
	/* Uninportant function. */
	int b = 0;

	b++;
	if (a > b)
		b++;
}

static int ldv_func1(int a) 
{
	/* Uninportant function, but there were predicates inserted. */
	int b = 0;

	b++;
	if (a > b)
		b++;

	return b;
}

static void *ldv_func2(void *arg)
{
	int p = 0;
	int b = ldv_undef_int();
	
	ldv_func3(p);
	b = ldv_func1(p);
	ldv_func4(p);

	if (b == 0)
		/* False unsafe. f should be cleaned after refinement. */
		_ldv_global_var++;

	/* True unsafe. */
	_ldv_global_var2++;

	return NULL;
}

static int __init ldv_init(void)
{
	pthread_t thread;
	pthread_attr_t const *attr = ldv_undef_ptr();
	void *arg = ldv_undef_ptr();

	pthread_create(&thread, attr, &ldv_func2, arg);
	mutex_lock(&ldv_lock);
	_ldv_global_var++;
	_ldv_global_var2++;
	mutex_unlock(&ldv_lock);

	return 0;
}

module_init(ldv_init);
