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
#include <linux/types.h>
#include <linux/kref.h>
#include <verifier/nondet.h>

static DEFINE_MUTEX(ldv_lock1);
static DEFINE_MUTEX(ldv_lock2);
static DEFINE_MUTEX(ldv_lock3);

static void ldv_release(struct kref *kref)
{
}

static int __init ldv_init(void)
{
	unsigned int subclass = ldv_undef_uint();
	struct kref kref;
	atomic_t cnt;

	kref_init(&kref);
	atomic_set(&cnt, ldv_undef_int());

	mutex_lock(&ldv_lock1);
	mutex_lock_nested(&ldv_lock2, subclass);
	kref_put_mutex(&kref, ldv_release, &ldv_lock3);
	mutex_unlock(&ldv_lock1);
	mutex_unlock(&ldv_lock2);
	mutex_unlock(&ldv_lock3);
	
	if (!mutex_lock_interruptible(&ldv_lock1))
		mutex_unlock(&ldv_lock1);

	if (!mutex_lock_killable(&ldv_lock1))
		mutex_unlock(&ldv_lock1);

	if (mutex_trylock(&ldv_lock1))
		mutex_unlock(&ldv_lock1);

	if (atomic_dec_and_mutex_lock(&cnt, &ldv_lock1))
		mutex_unlock(&ldv_lock1);

	mutex_lock(&ldv_lock1);
	if (mutex_is_locked(&ldv_lock1))
		mutex_unlock(&ldv_lock1);

	return 0;
}

module_init(ldv_init);
