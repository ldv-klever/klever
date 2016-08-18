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

/* CHANGE_STATE Indicates the level of rcu_lock nesting */
int ldv_rcu_nested_sched = 0;

/* MODEL_FUNC_DEF Entry in rcu_read_lock/unlock section */
void ldv_rcu_read_lock_sched(void)
{
	/* CHANGE_STATE Increments the level of rcu_read_lock nesting */
	ldv_rcu_nested_sched++;
}

/* MODEL_FUNC_DEF Exit from rcu_read_lock/unlock section */
void ldv_rcu_read_unlock_sched(void)
{
	/* ASSERT checks the count of opened rcu_lock sections */
	ldv_assert("linux:rculocksched::more unlocks", ldv_rcu_nested_sched > 0);
	/* CHANGE_STATE Decrements the level of rcu_lock nesting */
	ldv_rcu_nested_sched--;
}

/* MODEL_FUNC_DEF Checks that all rcu_lock sections are closed at read sections */
void ldv_check_for_read_section( void )
{
	/* ASSERT checks the count of opened rcu_lock sections */
	ldv_assert("linux:rculocksched::locked at read section", ldv_rcu_nested_sched == 0);
}

/* MODEL_FUNC_DEF Checks that all rcu_lock sections are closed at exit */
void ldv_check_final_state( void )
{
	/* ASSERT checks the count of opened rcu_lock sections */
	ldv_assert("linux:rculocksched::locked at exit", ldv_rcu_nested_sched == 0);
}
