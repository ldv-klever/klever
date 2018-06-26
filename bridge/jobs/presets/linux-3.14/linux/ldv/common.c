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
 * ee the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <linux/ldv/common.h>
#include <verifier/common.h>

/*
 * Trivial model for interrupt context. Likely it is correct just in case of
 * single thread executed on single CPU core.
 */
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

static int ldv_filter_positive_int(int val)
{
	ldv_assume(val <= 0);
	return val;
}

/*
 * Implicitly filter positive integers for all undefined functions. See more
 * details at https://forge.ispras.ru/issues/7140.
 */
int ldv_post_init(int init_ret_val)
{
	return ldv_filter_positive_int(init_ret_val);
}

/* Like ldv_post_init(). */
int ldv_post_probe(int probe_ret_val)
{
	return ldv_filter_positive_int(probe_ret_val);
}

/* Like ldv_post_init(). */
int ldv_filter_err_code(int ret_val)
{
	return ldv_filter_positive_int(ret_val);
}
