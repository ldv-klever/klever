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

/*
 * Trivial model for interrupt context. Likely it is correct just in case of
 * single thread executed on single CPU core.
 */
#include <linux/types.h>
#include <linux/ldv/irq.h>

static bool __ldv_in_interrupt_context = false;

/* MODEL_FUNC Switch to interrupt context */
void ldv_switch_to_interrupt_context(void)
{
	__ldv_in_interrupt_context = true;
}

/* MODEL_FUNC Switch to process context */
void ldv_switch_to_process_context(void)
{
	__ldv_in_interrupt_context = false;
}

bool ldv_in_interrupt_context(void)
{
	return __ldv_in_interrupt_context;
}
