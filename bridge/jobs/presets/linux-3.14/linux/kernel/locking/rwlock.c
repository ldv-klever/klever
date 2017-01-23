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

/* MODEL_FUNC Check that write lock was not locked and lock read lock. */
void ldv_read_lock(rwlock_t *lock)
{
	if (ldv_set_contains(LDV_WLOCKS, lock))
		/* WARN Write lock must be unlocked. */
		ldv_warn("linux:kernel:locking:rwlock::one thread:read lock on write lock");

	/* NOTE Lock read lock. */
	ldv_set_add(LDV_RLOCKS, lock);
}

/* MODEL_FUNC Check that read lock was locked and unlock it. */
void ldv_read_unlock(rwlock_t *lock)
{
	if (!ldv_set_contains(LDV_RLOCKS, lock))
		/* WARN Read lock must be locked. */
		ldv_warn("linux:kernel:locking:rwlock::one thread:more read unlocks");

	/* NOTE Unlock read lock. */
	ldv_set_remove(LDV_RLOCKS, lock);
}

/* MODEL_FUNC Check that write lock was not locked and lock it. */
void ldv_write_lock(rwlock_t *lock)
{
	if (ldv_set_contains(LDV_WLOCKS, lock))
		/* WARN Write lock must be unlocked. */
		ldv_warn("linux:kernel:locking:rwlock::one thread:double write lock");

	/* NOTE Lock write lock. */
	ldv_set_add(LDV_WLOCKS, lock);
}

/* MODEL_FUNC Check that write lock was locked and unlock it. */
void ldv_write_unlock(rwlock_t *lock)
{
	if (!ldv_set_contains(LDV_WLOCKS, lock))
		/* WARN Write lock must be locked. */
		ldv_warn("linux:kernel:locking:rwlock::one thread:double write unlock");

	/* NOTE Unlock write lock. */
	ldv_set_remove(LDV_WLOCKS, lock);
}

/* MODEL_FUNC Lock read lock if it was not locked before. */
int ldv_read_trylock(rwlock_t *lock)
{
	if (!ldv_set_contains(LDV_WLOCKS, lock) && ldv_undef_int()) {
		/* NOTE Lock read lock since it was not locked before. */
		ldv_set_add(LDV_RLOCKS, lock);
		/* NOTE Successfully locked read lock. */
		return 1;
	}
	else {
		/* NOTE Read lock was locked before. */
		return 0;
	}
}

/* MODEL_FUNC Lock write lock if it was not locked before. */
int ldv_write_trylock(rwlock_t *lock)
{
	if (!ldv_set_contains(LDV_WLOCKS, lock) && ldv_undef_int()) {
		/* NOTE Lock write lock since it was not locked before. */
		ldv_set_add(LDV_WLOCKS, lock);
		/* NOTE Successfully locked write lock. */
		return 1;
	}
	else {
		/* NOTE Write lock was locked before. */
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
		ldv_warn("linux:kernel:locking:rwlock::one thread:read lock at exit");

	if (!ldv_set_is_empty(LDV_WLOCKS))
		/* WARN Write locks must be unlocked at the end. */
		ldv_warn("linux:kernel:locking:rwlock::one thread:write lock at exit");
}
