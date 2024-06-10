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

/*
 * Trivial model for interrupt context. Likely it is correct just in case of
 * single thread executed on single CPU core.
 */
static bool __ldv_in_interrupt_context = false;
static bool was_in_interrupt_context_schedule = false;
extern void ldv_save_spinlocks_schedule(void);
extern void ldv_restore_spinlocks_schedule(void);


void ldv_switch_to_interrupt_context(void)
{
	/* NOTE Switch to interrupt context */
	__ldv_in_interrupt_context = true;
}

void ldv_switch_to_process_context(void)
{
	/* NOTE Switch to process context */
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
	ldv_check_return_value_probe(probe_ret_val);
	return ldv_filter_positive_int(probe_ret_val);
}

/* Like ldv_post_init(). */
int ldv_filter_err_code(int ret_val)
{
	return ldv_filter_positive_int(ret_val);
}

void ldv_switch_to_context_for_schedule(void)
{
	was_in_interrupt_context_schedule = false;
  	if (__ldv_in_interrupt_context) {
      	/* NOTE Switch to process context for schedule*/
		was_in_interrupt_context_schedule = true;
      	__ldv_in_interrupt_context = false;
    }
  	ldv_save_spinlocks_schedule();
}

void ldv_switch_out_context_for_schedule(void)
{
  	if (was_in_interrupt_context_schedule) {
      	/* NOTE Switch back to interrupt context for schedule*/
      	__ldv_in_interrupt_context = true;
    }
  	was_in_interrupt_context_schedule = false;
  	ldv_restore_spinlocks_schedule();
}
