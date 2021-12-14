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

#include <ldv/linux/common.h>
#include <ldv/verifier/common.h>
#include <ldv/verifier/nondet.h>

/* NOTE Read lock is not acquired at the beginning */
int ldv_rlock = 1;
/* NOTE Write lock is not acquired at the beginning */
int ldv_wlock = 1;

void ldv_read_lock(void)
{
	if (ldv_wlock != 1)
		/* ASSERT Write lock should not be acquired */
		ldv_assert();

	/* NOTE Acquire read lock */
	ldv_rlock += 1;
}

void ldv_read_unlock(void)
{
	if (ldv_rlock <= 1)
		/* ASSERT Read lock should be acquired */
		ldv_assert();

	/* NOTE Release read lock */
	ldv_rlock -= 1;
}

void ldv_write_lock(void)
{
	if (ldv_wlock != 1)
		/* ASSERT Write lock should not be acquired */
		ldv_assert();

	/* NOTE Acquire write lock */
	ldv_wlock = 2;
}

void ldv_write_unlock(void)
{
	if (ldv_wlock == 1)
		/* ASSERT Write lock should be acquired */
		ldv_assert();

	/* NOTE Release write lock */
	ldv_wlock = 1;
}

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

void ldv_check_final_state(void)
{
	if (ldv_rlock != 1)
		/* ASSERT All acquired read locks should be released before finishing operation */
		ldv_assert();

	if (ldv_wlock != 1)
		/* ASSERT All acquired write locks should be released before finishing operation */
		ldv_assert();
}
