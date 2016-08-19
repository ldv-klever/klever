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

#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/types.h>
#include <linux/kref.h>

static DEFINE_MUTEX(mutex_1);
static DEFINE_MUTEX(mutex_2);
static DEFINE_MUTEX(mutex_3);

static void specific_func(struct kref *kref);

static int __init init(void)
{
	unsigned int num;
	struct kref *kref;
	atomic_t *counter;
	
	mutex_lock(&mutex_1);
	mutex_lock_nested(&mutex_2, num);
	kref_put_mutex(kref, specific_func, &mutex_3);
	mutex_unlock(&mutex_1);
	mutex_unlock(&mutex_2);
	mutex_unlock(&mutex_3);
	
	if (!mutex_lock_interruptible(&mutex_1))
		mutex_unlock(&mutex_1);
	if (!mutex_lock_killable(&mutex_1))
		mutex_unlock(&mutex_1);
	if (mutex_trylock(&mutex_1))
		mutex_unlock(&mutex_1);
	if (atomic_dec_and_mutex_lock(counter, &mutex_1))
		mutex_unlock(&mutex_1);
	mutex_lock(&mutex_1);
	if (mutex_is_locked(&mutex_1))
		mutex_unlock(&mutex_1);

	return 0;
}

module_init(init);
