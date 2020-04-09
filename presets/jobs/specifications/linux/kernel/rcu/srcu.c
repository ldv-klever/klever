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

/* NOTE Indicates the level of srcu_lock nesting */
int ldv_srcu_nested = 0;

void ldv_srcu_read_lock(void)
{
	/* NOTE Entry in srcu_read_lock/unlock section */
	ldv_srcu_nested++;
}

void ldv_srcu_read_unlock(void)
{
	/* ASSERT checks the count of opened srcu_lock sections */
	ldv_assert(ldv_srcu_nested > 0);
	/* NOTE Exit from srcu_read_lock/unlock section */
	ldv_srcu_nested--;
}

void ldv_check_for_read_section( void )
{
	/* ASSERT All srcu_lock sections should be closed at read sections */
	ldv_assert(ldv_srcu_nested == 0);
}

void ldv_check_final_state( void )
{
	/* ASSERT All srcu_lock sections should be closed at exit */
	ldv_assert(ldv_srcu_nested == 0);
}
