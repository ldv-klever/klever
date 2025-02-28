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
static int _ldv_global_var;

extern int _ldv_print(const char *s, int);

static int ldv_print(void)
{
	mutex_lock(&ldv_lock);
	if (_ldv_global_var % 2 == 0)
		_ldv_print("global is even: %d", _ldv_global_var);
	else
		_ldv_print("global is odd: %d", _ldv_global_var);
	mutex_unlock(&ldv_lock);

	return 0;
}

static int ldv_increase(void)
{
	mutex_lock(&ldv_lock);
	_ldv_global_var++;
	mutex_unlock(&ldv_lock);

	return 0;
}

static void *ldv_main(void *arg)
{
	switch (ldv_undef_int()) {
	case 0:
		ldv_print();
		break;
	case 1:
		ldv_increase();
		break;
	}

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
