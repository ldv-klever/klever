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

#include <linux/ldv/common.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

/* Module reference counter that shouldn't go lower its initial state. We do not distinguish different modules. */
/* NOTE Set module reference counter initial value at the beginning */
int ldv_module_refcounter = 1;

/* MODEL_FUNC Increment module reference counter unless module pointer is NULL */
void ldv_module_get(struct module *module)
{
	/* NOTE Do nothing if module pointer is NULL */
	if (module) {
		/* NOTE Increment module reference counter */
		ldv_module_refcounter++;
	}
}

/* MODEL_FUNC Nondeterministically increment module reference counter unless module pointer is NULL */
int ldv_try_module_get(struct module *module)
{
	/* NOTE Do nothing if module pointer is NULL */
	if (module) {
		/* NOTE Nondeterministically increment module reference counter */
		if (ldv_undef_int() == 1) {
			/* NOTE Increment module reference counter */
			ldv_module_refcounter++;
			/* NOTE Successfully incremented module reference counter */
			return 1;
		}
		else {
			/* NOTE Could not increment module reference counter */
			return 0;
		}
	}
}

/* MODEL_FUNC Check that module reference counter is greater than its initial state and decrement it unless module pointer is NULL */
void ldv_module_put(struct module *module)
{
	/* NOTE Do nothing if module pointer is NULL */
	if (module) {
		/* ASSERT Decremented module reference counter should be greater than its initial state */
		ldv_assert("linux:kernel:module::less initial decrement", ldv_module_refcounter > 1);
		/* NOTE Decrement module reference counter */
		ldv_module_refcounter--;
	}
}

/* MODEL_FUNC Check that module reference counter is greater than its initial state, decrement it and stop execution */
void ldv_module_put_and_exit(void)
{
	/* MODEL_FUNC_CALL Decrement module reference counter */ 
	ldv_module_put((struct module *)1);
	/* TODO: indeed this can result in missing bugs because of final state won't be checked. Safe test shows that. */
	/* NOTE Stop execution */
	LDV_STOP: goto LDV_STOP;
}

/* MODEL_FUNC Get module reference counter */
unsigned int ldv_module_refcount(void)
{
	/* NOTE Return module reference counter */
	return ldv_module_refcounter - 1;
}

/* MODEL_FUNC Check that module reference counter has its initial value at the end */
void ldv_check_final_state(void)
{
	/* ASSERT Module reference counter should be decremented to its initial value before finishing operation */
	ldv_assert("linux:kernel:module::more initial at exit", ldv_module_refcounter == 1);
}
