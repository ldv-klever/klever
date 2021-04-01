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

#include <linux/gfp.h>
#include <ldv/linux/slab.h>
#include <ldv/linux/common.h>
#include <ldv/verifier/common.h>

void ldv_check_alloc_flags(gfp_t flags) 
{
	if (ldv_in_interrupt_context() && flags != GFP_ATOMIC)
		/* ASSERT GFP_ATOMIC flag should be used in context of interrupt */
		ldv_assert();
}

void ldv_check_alloc_nonatomic(void)
{
	if (ldv_in_interrupt_context())
		/* ASSERT We should not be in context of interrupt */
		ldv_assert();
}
