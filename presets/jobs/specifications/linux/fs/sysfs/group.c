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

int ldv_sysfs = 0;

int ldv_sysfs_create_group(void)
{
	/* NOTE Choose an arbitrary return value. */
	int res = ldv_undef_int_nonpositive();

	if (!res) {
		/* NOTE Increase allocated counter. */
		ldv_sysfs++;
		/* NOTE Sysfs group was successfully created. */
		return 0;
	}

	/* NOTE There was an error during sysfs group creation. */
	return res;
}

void ldv_sysfs_remove_group(void)
{
	if (ldv_sysfs < 1)
		/* ASSERT Sysfs group must be allocated before. */
		ldv_assert();

	/* NOTE Decrease allocated counter. */
	ldv_sysfs--;
}

void ldv_check_final_state( void )
{
	if (ldv_sysfs != 0)
		/* ASSERT Sysfs groups must be freed at the end. */
		ldv_assert();
}
