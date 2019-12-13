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

#include <linux/ldv/common.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

/* NOTE Indicates the level of rcu_lock nesting */
int ldv_rcu_nested_sched = 0;

void ldv_rcu_read_lock_sched(void)
{
	/* NOTE Entry in rcu_read_lock/unlock section */
	ldv_rcu_nested_sched++;
}

void ldv_rcu_read_unlock_sched(void)
{
	/* ASSERT checks the count of opened rcu_lock sections */
	ldv_assert(ldv_rcu_nested_sched > 0);
	/* NOTE Exit from rcu_read_lock/unlock section */
	ldv_rcu_nested_sched--;
}

void ldv_check_for_read_section( void )
{
	/* ASSERT All rcu_lock sections should be closed at read sections */
	ldv_assert(ldv_rcu_nested_sched == 0);
}

void ldv_check_final_state( void )
{
	/* ASSERT All rcu_lock sections should be closed at exit */
	ldv_assert(ldv_rcu_nested_sched == 0);
}
