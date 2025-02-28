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

#include <linux/module.h>
#include <linux/mutex.h>
#include <ldv/verifier/nondet.h>
#include <ldv/verifier/thread.h>

static DEFINE_MUTEX(ldv_lock);
static int _ldv_global;

static int ldv_func3(int arg)
{
	int ldv_tmp = ldv_func3(arg);

	arg++;

	if (ldv_tmp > arg)
		ldv_tmp = ldv_tmp - arg;
	else {
		ldv_tmp = arg - ldv_tmp;
		_ldv_global++;
	}

	ldv_tmp = ldv_func3(ldv_tmp);
	ldv_tmp++;

	return ldv_tmp;
}
 
static int ldv_func2(int arg)
{
	int ldv_tmp = ldv_func3(arg);

	arg++;

	if (ldv_tmp > arg)
		ldv_tmp = ldv_tmp - arg;
	else
		ldv_tmp = arg - ldv_tmp;

	ldv_tmp = ldv_func3(ldv_tmp);
	ldv_tmp++;

	return ldv_tmp;
}
 
static int ldv_func1(int arg)
{
	int ldv_tmp = ldv_func2(arg);
	 
	arg++;

	if (ldv_tmp > arg)
		ldv_tmp = ldv_tmp - arg;
	else
		ldv_tmp = arg - ldv_tmp;

	ldv_tmp = ldv_func2(ldv_tmp);
	ldv_tmp++;

	return ldv_tmp;
}

static void *ldv_main(void *arg)
{
	int ldv_tmp = ldv_undef_int();
	
	ldv_func1(ldv_tmp);
	mutex_lock(&ldv_lock);
	ldv_func1(ldv_tmp++);
	mutex_unlock(&ldv_lock);

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
