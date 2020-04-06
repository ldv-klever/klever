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
#include <verifier/nondet.h>
#include <verifier/thread.h>

static DEFINE_MUTEX(ldv_lock);
static int _ldv_global_var;

static int ldv_func1(unsigned int ldv_cmd)
{
	switch (ldv_cmd) {
	case (1UL | (unsigned long)4):
		_ldv_global_var++;
		break;
	}
	
	return 0;
}

static void *ldv_func2(void *arg)
{
	ldv_func1(1UL | (unsigned long)4);
	return NULL;
}

static int __init ldv_init(void)
{
	pthread_t thread;
	pthread_attr_t const *attr = ldv_undef_ptr();
	void *arg = ldv_undef_ptr();

	pthread_create(&thread, attr, &ldv_func2, arg);
	mutex_lock(&ldv_lock);
	_ldv_global_var = 1;
	mutex_unlock(&ldv_lock);

	return 0;
}

module_init(ldv_init);
