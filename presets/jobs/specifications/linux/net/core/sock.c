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

#include <linux/types.h>
#include <linux/ldv/common.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

/* NOTE There is no locked sockets at the beginning */
int locksocknumber = 0;

void ldv_past_lock_sock_nested(void)
{
	/* NOTE locking socket */
	locksocknumber++;
}

bool ldv_lock_sock_fast(void)
{
	/* NOTE we dont know lock this socket or not */
	if (ldv_undef_int()) {
		/* NOTE locking socket*/
		locksocknumber++;
		/* NOTE Socket lock */
		return true; 
	}
	/* NOTE Cant lock socket */
	return false;
}

void ldv_unlock_sock_fast(void)
{
	/* ASSERT unlock_sock_fas negative locksocknumber the result of multiply releases */
	ldv_assert(locksocknumber > 0);
	/* NOTE unlocking socket fast warning*/
	locksocknumber--;
}

void ldv_before_release_sock(void)
{
	/* ASSERT lock_sock negative locksocknumber the result of multiply releases */
	ldv_assert(locksocknumber > 0);
	/* NOTE locked socket released */
	locksocknumber--;
}

void ldv_check_final_state(void)
{
	/* ASSERT lock_sock number */
	ldv_assert(locksocknumber == 0);
}
