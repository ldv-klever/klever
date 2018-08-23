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
 * ee the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <linux/ldv/common.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

/* NOTE Read lock is not aquired at the beginning */
int ldv_rlock = 1;
/* NOTE Write lock is not aquired at the beginning */
int ldv_wlock = 1;

/* MODEL_FUNC Check that write lock is not acquired and acquire read lock */
void ldv_read_lock(void)
{
	/* ASSERT Write lock should not be aquired */
	ldv_assert("linux:kernel:locking:rwlock::read lock on write lock", ldv_wlock == 1);
	/* NOTE Acquire read lock */
	ldv_rlock += 1;
}

/* MODEL_FUNC Check that read lock is acquired and release it */
void ldv_read_unlock(void)
{
	/* ASSERT Read lock should be acquired */
	ldv_assert("linux:kernel:locking:rwlock::more read unlocks", ldv_rlock > 1);
	/* NOTE Release read lock */
	ldv_rlock -= 1;
}

/* MODEL_FUNC Check that write lock is not aquired and acquire it */
void ldv_write_lock(void)
{
	/* ASSERT Write lock should not be aquired */
	ldv_assert("linux:kernel:locking:rwlock::double write lock", ldv_wlock == 1);
	/* NOTE Acquire write lock */
	ldv_wlock = 2;
}

/* MODEL_FUNC Check that write lock is aquired and release it */
void ldv_write_unlock(void)
{
	/* ASSERT Write lock should be aquired */
	ldv_assert("linux:kernel:locking:rwlock::double write unlock", ldv_wlock != 1);
	/* NOTE Release write lock */
	ldv_wlock = 1;
}

/* MODEL_FUNC Try to acquire read lock */
int ldv_read_trylock(void)
{
	/* NOTE Nondeterministically acquire read lock if write lock is not acquired */
	if (ldv_wlock == 1 && ldv_undef_int()) {
		/* NOTE Acquire read lock */
		ldv_rlock += 1;
		/* NOTE Read lock was acquired */
		return 1;
	}
	else {
		/* NOTE Read lock was not acquired */
		return 0;
	}
}

/* MODEL_FUNC Try to acquire write lock */
int ldv_write_trylock(void)
{
	/* NOTE Nondeterministically acquire write lock if it is not acquired */
	if (ldv_wlock == 1 && ldv_undef_int()) {
		/* NOTE Acquire write lock */
		ldv_wlock = 2;
		/* NOTE Write lock was not acquired */
		return 1;
	}
	else {
		/* NOTE Write lock was not acquired */
		return 0;
	}
}

/* MODEL_FUNC Check that all read/write locks are unacquired at the end */
void ldv_check_final_state(void)
{
	/* ASSERT All acquired read locks should be released before finishing operation */
	ldv_assert("linux:kernel:locking:rwlock::read lock at exit", ldv_rlock == 1);
	/* ASSERT All acquired write locks should be released before finishing operation */
	ldv_assert("linux:kernel:locking:rwlock::write lock at exit", ldv_wlock == 1);
}
