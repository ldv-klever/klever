/*
 * Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
 * Institute for System Programming of the Russian Academy of Sciences
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

#include <linux/types.h>
#include <linux/ldv/common.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

/* CHANGE_STATE There is no locked sockets at the beginning */
int locksocknumber = 0;

/* MODEL_FUNC_DEF executed after locking socket using nested function */
void ldv_past_lock_sock_nested(void)
{
        /* CHANGE_STATE locking socket */
	locksocknumber++;
}

/* MODEL_FUNC_DEF executed around locking socket using fast function */
bool ldv_lock_sock_fast(void)
{
	/* OTHER we dont know lock this socket or not */
	if (ldv_undef_int()) {
		/* CHANGE_STATE locking socket*/	
		locksocknumber++;
		/* RETURN Socket lock */
		return true; 
	}
	/* RETURN Cant lock socket */
	return false;
}

/* MODEL_FUNC_DEF executed around unlocking socket using fast function */
void ldv_unlock_sock_fast(void)
{
	/* ASSERT unlock_sock_fas negative locksocknumber the result of multiply releases */
	ldv_assert("linux:sock::double release", locksocknumber > 0);
	/* CHANGE_STATE unlocking socket fast warning*/
	locksocknumber--;
}

/* MODEL_FUNC_DEF executed after releasing socket */
void ldv_before_release_sock(void)
{
	/* ASSERT lock_sock negative locksocknumber the result of multiply releases */
	ldv_assert("linux:sock::double release", locksocknumber > 0);
	/* CHANGE_STATE locked socket released */
	locksocknumber--;
}

/* MODEL_FUNC_DEF check on exit */
void ldv_check_final_state(void)
{
	/* ASSERT lock_sock number */
	ldv_assert("linux:sock::all locked sockets must be released", locksocknumber == 0);
}
