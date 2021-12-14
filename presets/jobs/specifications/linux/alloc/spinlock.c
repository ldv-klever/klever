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

#include <ldv/linux/gfp.h>
#include <ldv/linux/slab.h>
#include <ldv/verifier/common.h>

extern int ldv_exclusive_spin_is_locked(void);

void ldv_check_alloc_flags(gfp_t flags)
{
	if (ldv_exclusive_spin_is_locked() && !CHECK_WAIT_FLAGS(flags))
		/* ASSERT __GFP_WAIT flag should be unset (GFP_ATOMIC or GFP_NOWAIT flag should be used) when spinlock is acquired */
		ldv_assert();
}

void ldv_check_alloc_nonatomic(void)
{
	if (ldv_exclusive_spin_is_locked())
		/* ASSERT Spinlock should not be acquired */
		ldv_assert();
}
