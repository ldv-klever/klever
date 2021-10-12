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

/* There are 2 possible model states. */
enum
{
	LDV_PROBE_ZERO_STATE = 0, /* No error occurred. */
	LDV_PROBE_ERROR = 1,      /* Error occurred. probe() should return error code (or at least not zero). */
};

/* NOTE Model automaton state (one of two possible ones) */
int ldv_probe_state = LDV_PROBE_ZERO_STATE;

void ldv_failed_register_netdev(void)
{
	/* NOTE Error occurred */
	ldv_probe_state = LDV_PROBE_ERROR;
}

void ldv_reset_error_counter(void)
{
	/* NOTE Reset error counter from previous calls */
	ldv_probe_state = LDV_PROBE_ZERO_STATE;
}

void ldv_pre_probe(void)
{
	ldv_reset_error_counter();
}

int ldv_post_init(int init_ret_val)
{
	ldv_reset_error_counter();
}

void ldv_check_return_value_probe(int retval)
{
	if (ldv_probe_state == LDV_PROBE_ERROR && retval == 0)
		/* ASSERT Errors of register_netdev() should be properly propagated */
		ldv_assert();

	/* NOTE Prevent error counter from being checked in other functions */
	ldv_reset_error_counter();
}
