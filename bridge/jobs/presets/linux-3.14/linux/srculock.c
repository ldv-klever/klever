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

#include <linux/ldv/common.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

/* CHANGE_STATE Indicates the level of srcu_lock nesting */
int ldv_srcu_nested = 0;

/* MODEL_FUNC_DEF Entry in srcu_read_lock/unlock section */
void ldv_srcu_read_lock(void)
{
	/* CHANGE_STATE Increments the level of srcu_read_lock nesting */
	ldv_srcu_nested++;
}

/* MODEL_FUNC_DEF Exit from srcu_read_lock/unlock section */
void ldv_srcu_read_unlock(void)
{
	/* ASSERT checks the count of opened srcu_lock sections */
	ldv_assert("linux:srculock::more unlocks", ldv_srcu_nested > 0);
	/* CHANGE_STATE Decrements the level of srcu_lock nesting */
	ldv_srcu_nested--;
}

/* MODEL_FUNC_DEF Checks that all srcu_lock sections are closed at read sections */
void ldv_check_for_read_section( void )
{
	/* ASSERT checks the count of opened srcu_lock sections */
	ldv_assert("linux:srculock::locked at read section", ldv_srcu_nested == 0);
}

/* MODEL_FUNC_DEF Checks that all srcu_lock sections are closed at exit.*/
void ldv_check_final_state( void )
{
	/* ASSERT checks the count of opened srcu_lock sections */
	ldv_assert("linux:srculock::locked at exit", ldv_srcu_nested == 0);
}
