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

#include <linux/spinlock_types.h>
#include <linux/ldv/common.h>
#include <linux/ldv/kernel/locking/rwlock.h>
#include <verifier/common.h>
#include <verifier/nondet.h>
#include <verifier/set.h>

static ldv_set LDV_RLOCKS;
static ldv_set LDV_WLOCKS;

/* MODEL_FUNC Check that write lock is not acquired and acquire read lock. */
void ldv_read_lock(rwlock_t *lock)
{
	if (ldv_set_contains(LDV_WLOCKS, lock))
		/* WARN Write lock should not be aquired. */
		ldv_warn("linux:kernel:locking:rwlock::read lock on write lock");

	/* NOTE Acquire read lock. */
	ldv_set_add(LDV_RLOCKS, lock);
}

/* MODEL_FUNC Check that read lock is acquired and release it. */
void ldv_read_unlock(rwlock_t *lock)
{
	if (!ldv_set_contains(LDV_RLOCKS, lock))
		/* WARN Read lock should be acquired. */
		ldv_warn("linux:kernel:locking:rwlock::more read unlocks");

	/* NOTE Release read lock. */
	ldv_set_remove(LDV_RLOCKS, lock);
}

/* MODEL_FUNC Check that write lock is not aquired and acquire it. */
void ldv_write_lock(rwlock_t *lock)
{
	if (ldv_set_contains(LDV_WLOCKS, lock))
		/* WARN Write lock should not be aquired. */
		ldv_warn("linux:kernel:locking:rwlock::double write lock");

	/* NOTE Acquire write lock. */
	ldv_set_add(LDV_WLOCKS, lock);
}

/* MODEL_FUNC Check that write lock is aquired and release it. */
void ldv_write_unlock(rwlock_t *lock)
{
	if (!ldv_set_contains(LDV_WLOCKS, lock))
		/* WARN Write lock should be aquired. */
		ldv_warn("linux:kernel:locking:rwlock::double write unlock");

	/* NOTE Release write lock. */
	ldv_set_remove(LDV_WLOCKS, lock);
}

/* MODEL_FUNC Try to acquire read lock. */
int ldv_read_trylock(rwlock_t *lock)
{
	if (!ldv_set_contains(LDV_WLOCKS, lock) && ldv_undef_int()) {
		/* NOTE Acquire read lock. */
		ldv_set_add(LDV_RLOCKS, lock);
		/* NOTE Read lock was acquired. */
		return 1;
	}
	else {
		/* NOTE Read lock was not acquired. */
		return 0;
	}
}

/* MODEL_FUNC Try to acquire write lock. */
int ldv_write_trylock(rwlock_t *lock)
{
	if (!ldv_set_contains(LDV_WLOCKS, lock) && ldv_undef_int()) {
		/* NOTE Acquire write lock. */
		ldv_set_add(LDV_WLOCKS, lock);
		/* NOTE Write lock was not acquired. */
		return 1;
	}
	else {
		/* NOTE Write lock was not acquired. */
		return 0;
	}
}

/* MODEL_FUNC Make all read/write locks unlocked at the beginning. */
void ldv_initialize(void)
{
	/* NOTE Read locks are unlocked at the beginning. */
	ldv_set_init(LDV_RLOCKS);
	/* NOTE Write locks are unlocked at the beginning. */
	ldv_set_init(LDV_WLOCKS);
}

/* MODEL_FUNC Check that all read/write locks are unlocked at the end. */
void ldv_check_final_state(void)
{
	if (!ldv_set_is_empty(LDV_RLOCKS))
		/* WARN Read locks must be unlocked at the end. */
		ldv_warn("linux:kernel:locking:rwlock::read lock at exit");

	if (!ldv_set_is_empty(LDV_WLOCKS))
		/* WARN Write locks must be unlocked at the end. */
		ldv_warn("linux:kernel:locking:rwlock::write lock at exit");
}
