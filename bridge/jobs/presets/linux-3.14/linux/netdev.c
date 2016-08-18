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

/* There are 2 possible model states. */
enum
{
	LDV_PROBE_ZERO_STATE = 0, /* No error occured. */
	LDV_PROBE_ERROR = 1,      /* Error occured. probe() should return error code (or at least not zero). */
};

/* CHANGE_STATE Model automaton state (one of two possible ones) */
int ldv_probe_state = LDV_PROBE_ZERO_STATE;

/* MODEL_FUNC_DEF Nondeterministically change state after call to register_netdev() */
int ldv_pre_register_netdev(void)
{
	int nondet = ldv_undef_int();

	/* OTHER Nondeterministically report error */
	if (nondet < 0) {
		/* CHANGE_STATE Error occured */
		ldv_probe_state = LDV_PROBE_ERROR;
		/* RETURN Return error code */
		return nondet;
	}
	else {
		/* RETURN Assume no error occured */
		return 0;
	}
}

/* MODEL_FUNC_DEF Reset error counter from previous calls */
void ldv_reset_error_counter(void)
{
	/* CHANGE_STATE Reset counter */
	ldv_probe_state = LDV_PROBE_ZERO_STATE;
}

/* MODEL_FUNC_DEF Check that error code was properly propagated in probe() */
void ldv_check_return_value_probe(int retval)
{
	if (ldv_probe_state == LDV_PROBE_ERROR) {
		/* ASSERT Errors of register_netdev() should be properly propagated */
		ldv_assert("linux:netdev::wrong return value", retval != 0);
	}
	/* OTHER Prevent error counter from being checked in other functions */
	ldv_reset_error_counter();
}
