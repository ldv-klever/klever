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
int ldv_rcu_nested_bh = 0;

/* MODEL_FUNC Entry in rcu_read_lock/unlock section */
void ldv_rcu_read_lock_bh(void)
{
	/* NOTE Increments the level of rcu_read_lock nesting */
	ldv_rcu_nested_bh++;
}

/* MODEL_FUNC Exit from rcu_read_lock/unlock section */
void ldv_rcu_read_unlock_bh(void)
{
	/* ASSERT checks the count of opened rcu_lock sections */
	ldv_assert("linux:kernel:rcu:update:lock bh::more unlocks", ldv_rcu_nested_bh > 0);
	/* NOTE Decrements the level of rcu_lock nesting */
	ldv_rcu_nested_bh--;
}

/* MODEL_FUNC Checks that all rcu_lock sections are closed at read sections */
void ldv_check_for_read_section( void )
{
	/* ASSERT checks the count of opened rcu_lock sections */
	ldv_assert("linux:kernel:rcu:update:lock bh::locked at read section", ldv_rcu_nested_bh == 0);
}

/* MODEL_FUNC Checks that all rcu_lock sections are closed at exit */
void ldv_check_final_state( void )
{
	/* ASSERT checks the count of opened rcu_lock sections */
	ldv_assert("linux:kernel:rcu:update:lock bh::locked at exit", ldv_rcu_nested_bh == 0);
}
