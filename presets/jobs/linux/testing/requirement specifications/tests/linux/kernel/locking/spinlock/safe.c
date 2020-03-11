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
#include <linux/spinlock.h>
#include <linux/atomic.h>
#include <verifier/nondet.h>

static DEFINE_SPINLOCK(ldv_lock1);
static DEFINE_SPINLOCK(ldv_lock2);

static int __init ldv_init(void)
{
	atomic_t atomic;

	atomic_set(&atomic, ldv_undef_int());

	spin_lock(&ldv_lock1);
	spin_lock(&ldv_lock2);
	spin_unlock(&ldv_lock2);
	spin_unlock(&ldv_lock1);

	if (spin_trylock(&ldv_lock1))
		spin_unlock(&ldv_lock1);

	spin_lock(&ldv_lock1);
	if (spin_is_locked(&ldv_lock1))
		spin_unlock(&ldv_lock1);

	spin_lock(&ldv_lock1);
	if (!spin_can_lock(&ldv_lock1))
		spin_unlock(&ldv_lock1);

	if (atomic_dec_and_lock(&atomic, &ldv_lock1))
		spin_unlock(&ldv_lock1);

	return 0;
}

module_init(ldv_init);
