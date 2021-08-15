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

/* Define this macro to get proper value for macro THIS_MODULE. */
#define MODULE
#include <linux/export.h>
#include <ldv/linux/common.h>
#include <ldv/verifier/common.h>
#include <ldv/verifier/nondet.h>

struct module;

/* Module reference counter that shouldn't go lower its initial state. We do not distinguish different modules. */
/* NOTE Set module reference counter initial value at the beginning */
int ldv_module_refcounter = 1;

void ldv_module_get(struct module *module)
{
	/* NOTE Do nothing if module pointer is NULL */
	if (module) {
		/* NOTE Increment module reference counter */
		ldv_module_refcounter++;
	}
}

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

void ldv_module_put(struct module *module)
{
	/* NOTE Do nothing if module pointer is NULL */
	if (module) {
		if (ldv_module_refcounter <= 1)
			/* ASSERT Decremented module reference counter should be greater than its initial state */
			ldv_assert();

		/* NOTE Decrement module reference counter */
		ldv_module_refcounter--;
	}
}

void ldv_module_put_and_exit(void)
{
	ldv_module_put(THIS_MODULE);
	/* TODO: indeed this can result in missing bugs because of final state won't be checked. Safe test shows that. */
	/* NOTE Stop execution */
	LDV_STOP: goto LDV_STOP;
}

unsigned int ldv_module_refcount(void)
{
	/* NOTE Return module reference counter */
	return ldv_module_refcounter - 1;
}

void ldv_check_final_state(void)
{
	if (ldv_module_refcounter != 1)
		/* ASSERT Module reference counter should be decremented to its initial value before finishing operation */
		ldv_assert();
}
