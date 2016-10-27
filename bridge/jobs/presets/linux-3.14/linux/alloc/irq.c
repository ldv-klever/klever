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

#include <linux/gfp.h>
#include <linux/ldv/common.h>
#include <linux/ldv/irq.h>
#include <verifier/common.h>

/* MODEL_FUNC Check that flags GFP_ATOMIC or GFP_NOWAIT are used when allocating memory in interrupt context */
void ldv_check_alloc_flags(gfp_t flags) 
{
	if (ldv_in_interrupt_context())
		if (flags != GFP_ATOMIC)
			/* ASSERT Flags GFP_ATOMIC or GFP_NOWAIT should be used when allocating memory in interrupt context */
			ldv_assert("linux:alloc:irq::wrong flags", 0);
}

/* MODEL_FUNC Check that we are not in context of interrupt */
void ldv_check_alloc_nonatomic(void)
{
	if (ldv_in_interrupt_context())
	{
		/* ASSERT We should not be in context of interrupt */
		ldv_assert("linux:alloc:irq::nonatomic", 0);
	}
}
