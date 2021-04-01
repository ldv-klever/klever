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
#include <ldv/linux/err.h>
#include <ldv/verifier/common.h>
#include <ldv/verifier/nondet.h>

struct class;

/* There are 2 possible states of class structure registration. */
enum
{
	LDV_CLASS_ZERO_STATE, /* Class structure is not registered. */
	LDV_CLASS_REGISTERED  /* Class structure is registered. */
};

/* NOTE Usb gadget class is not registered at the beginning */
int ldv_usb_gadget_class = LDV_CLASS_ZERO_STATE;

void *ldv_create_class(void)
{
	void *is_got;

	/* NOTE Get blk request in the nondeterministic way */
	is_got = ldv_undef_ptr();

	/* NOTE Function cannot return NULL */
	ldv_assume(is_got);

	/* NOTE Get blk request just in case when an error did not happen */
	if (!ldv_is_err(is_got))
	{
		if (ldv_usb_gadget_class != LDV_CLASS_ZERO_STATE)
			/* ASSERT Check that usb gadget class is unregistered */
			ldv_assert();

		/* NOTE Register class for usb gadget */
		ldv_usb_gadget_class = LDV_CLASS_REGISTERED;
	}

	/* NOTE Return obtained blk request */
	return is_got;
}

int ldv_register_class(void)
{
	int is_reg;

	/* NOTE Register gadget class in the nondeterministic way */
	is_reg = ldv_undef_int_nonpositive();

	/* NOTE Get blk request just in case when an error did not happen */
	if (!is_reg)
	{
		if (ldv_usb_gadget_class != LDV_CLASS_ZERO_STATE)
			/* ASSERT Check that usb gadget class is unregistered */
			ldv_assert();

		/* NOTE Register class for usb gadget */
		ldv_usb_gadget_class = LDV_CLASS_REGISTERED;
	}

	/* NOTE Return registration status (0 is success) */
	return is_reg;
}

void ldv_unregister_class(void)
{
	if (ldv_usb_gadget_class != LDV_CLASS_REGISTERED)
		/* ASSERT Check that usb gadget class is registered */
		ldv_assert();

	/* NOTE Unregister class for usb gadget */
	ldv_usb_gadget_class = LDV_CLASS_ZERO_STATE;
}

void ldv_destroy_class(struct class *cls)
{
    if ((cls == 0) || (ldv_is_err(cls)))
        return;
    ldv_unregister_class();
}

void ldv_check_final_state(void)
{
	if (ldv_usb_gadget_class != LDV_CLASS_ZERO_STATE)
		/* ASSERT Usb gadget class should be unregistered at the end */
		ldv_assert();
}
