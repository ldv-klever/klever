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
static DEFINE_MUTEX(ldv_lock2);
static int _ldv_false_unsafe;
static int _ldv_true_unsafe;
static int _ldv_false_unsafe2;

__inline static int local_init(int mutex)
{ 
	int mtx = ldv_undef_int(), rt = ldv_undef_int();

	if (mutex == (unsigned int )(138 << 24)) {
		if (rt)
			return 0;

		mutex_lock(&ldv_lock);

		if (mtx != 0)
			return mtx;

		mutex_unlock(&ldv_lock);
	}

	return 0;
}

 __inline static int tryLock(int id___0) 
{ 
	int idx = ldv_undef_int();

	if (id___0 == 0)
		return 0;

	mutex_lock(&ldv_lock);

	if (id___0 == idx)
		return 1;

	mutex_unlock(&ldv_lock);

	return 0;
}

__inline static int get(int mutex)
{ 
	int rt = ldv_undef_int(), mtx, tmp___1;

	if (mutex == 0)
		return 0;

	mtx = tryLock(rt);

	if (mtx != 0)
		return mtx;

	tmp___1 = local_init(mutex);

	return tmp___1;
}
 
__inline static int check(int code)
{ 
	int tmp = ldv_undef_int();

	if (code == 27) {
		tmp = tryLock(tmp);
		if (tmp == 0)
			return 28;
	}

	return code;
}

static int difficult_function(void)
{
	int ret, param = ldv_undef_int();
	int mutex = ldv_undef_int();
	
	ret = get(mutex);
	if (ret == 0)
		return 28;

restart: 
	_ldv_false_unsafe = 0;
	_ldv_true_unsafe = 0;
	
	mutex_unlock(&ldv_lock);
	ret = check(param);

	if (ret == 27)
		goto restart;

	return 0;
}


static int f(int i)
{
	if (i >= 0) {
		mutex_lock(&ldv_lock2);
		_ldv_false_unsafe2 = 1;
		mutex_unlock(&ldv_lock2);
	} else
		_ldv_false_unsafe2 = 1;

	return 0;
}

static int my_main(int i)
{
	difficult_function();
	f(i);

	return 0;
}

static void *ldv_main(void *arg)
{
	my_main(0);
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
