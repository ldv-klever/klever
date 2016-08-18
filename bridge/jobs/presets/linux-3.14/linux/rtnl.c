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

#include <linux/ldv/common.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

void rtnl_lock(void);
void rtnl_unlock(void);

/* CHANGE_STATE There is no rtnllock at the beginning */
int rtnllocknumber = 0;

/* MODEL_FUNC_DEF executed after rtnl_unlock */
void ldv_past_rtnl_unlock(void)
{
	/* ASSERT double rtnl_unlock */
	ldv_assert("linux:rtnl::double unlock", rtnllocknumber == 1);
	/* CHANGE_STATE unlocking */
	rtnllocknumber=0;
}

/* MODEL_FUNC_DEF executed after rtnl_lock */
void ldv_past_rtnl_lock(void)
{
	/* ASSERT double rtnl_lock */
	ldv_assert("linux:rtnl::double lock", rtnllocknumber == 0);
	/* CHANGE_STATE locking */
	rtnllocknumber=1;
}

/* MODEL_FUNC_DEF executed before ieee80211_unregister_hw */
void ldv_before_ieee80211_unregister_hw(void)
{
	/* OTHER Modeling lock */
	ldv_past_rtnl_lock();
	/* OTHER Modeling unlock */
	ldv_past_rtnl_unlock();
}

/* MODEL_FUNC_DEF rtnl is locked */
int ldv_rtnl_is_locked(void)
{
	/* OTHER If we know about lock */
	if (rtnllocknumber)
		/* RETURN rtnl_lock by this thread */
		return rtnllocknumber;
	/* OTHER If we dont know about lock */
	else if (ldv_undef_int())
		/* RETURN rtnl_lock by another thread */
		return 1;
	else 	
		/* RETURN There is no rtnl_lock */
		return 0;
}

/* MODEL_FUNC_DEF trylock */
int ldv_rtnl_trylock(void)
{
	/* ASSERT double rtnl_trylock */
	ldv_assert("linux:rtnl::double lock", rtnllocknumber == 0);
	/* OTHER If there is no rtnl_lock */
	if (!ldv_rtnl_is_locked()) { 
		/* CHANGE_STATE locking by trylock */
		rtnllocknumber=1;
		/* RETURN Lock set */
		return 1;
	}
	/* RETURN Cant set lock */
	else return 0;
}

/* MODEL_FUNC_DEF check on exit */
void ldv_check_final_state(void)
{
	/* ASSERT lock_sock number */
	ldv_assert("linux:rtnl::lock on exit", rtnllocknumber == 0);
}
