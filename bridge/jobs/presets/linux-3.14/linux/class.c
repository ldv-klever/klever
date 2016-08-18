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
#include <linux/ldv/err.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

struct class;

/* There are 2 possible states of class structure registration. */
enum
{
	LDV_CLASS_ZERO_STATE, /* Class structure is not registered. */
	LDV_CLASS_REGISTERED  /* Class structure is registered. */
};

/* CHANGE_STATE Usb gadget class is not registered at the beginning */
int ldv_usb_gadget_class = LDV_CLASS_ZERO_STATE;

/* MODEL_FUNC_DEF Check that class was not registered. Then create and register class for it */
void *ldv_create_class(void)
{
	void *is_got;

	/* OTHER Get blk request in the nondeterministic way */
	is_got = ldv_undef_ptr();

	/* OTHER Function cannot return NULL */
	ldv_assume(is_got);

	/* ASSERT Get blk request just in case when an error did not happen */
	if (!ldv_is_err(is_got))
	{
		/* ASSERT Check that usb gadget class is unregistered */
		ldv_assert("linux:class::double registration", ldv_usb_gadget_class == LDV_CLASS_ZERO_STATE);
		/* CHANGE_STATE Register class for usb gadget */
		ldv_usb_gadget_class = LDV_CLASS_REGISTERED;
	}

	/* RETURN Return obtained blk request */
	return is_got;
}

/* MODEL_FUNC_DEF Check that class was not registered and register class for it */
int ldv_register_class(void)
{
	int is_reg;

	/* OTHER Register gadget class in the nondeterministic way */
	is_reg = ldv_undef_int_nonpositive();

	/* ASSERT Get blk request just in case when an error did not happen */
	if (!is_reg)
	{
		/* ASSERT Check that usb gadget class is unregistered */
		ldv_assert("linux:class::double registration", ldv_usb_gadget_class == LDV_CLASS_ZERO_STATE);
		/* CHANGE_STATE Register class for usb gadget */
		ldv_usb_gadget_class = LDV_CLASS_REGISTERED;
	}

	/* RETURN Return registration status (0 is success) */
	return is_reg;
}

/* MODEL_FUNC_DEF Check that class was registered and unregister it */
void ldv_unregister_class(void)
{
	/* ASSERT Check that usb gadget class is registered */
	ldv_assert("linux:class::double deregistration", ldv_usb_gadget_class == LDV_CLASS_REGISTERED);
	/* CHANGE_STATE Unregister class for usb gadget */
	ldv_usb_gadget_class = LDV_CLASS_ZERO_STATE;
}

void ldv_destroy_class(struct class *cls)
{
    if ((cls == 0) || (ldv_is_err(cls)))
        return;
    ldv_unregister_class();
}

/* MODEL_FUNC_DEF Check that usb gadget is fully unregistered at the end */
void ldv_check_final_state(void)
{
	/* ASSERT Usb gadget class should be unregistered at the end */
	ldv_assert("linux:class::registered at exit", ldv_usb_gadget_class == LDV_CLASS_ZERO_STATE);
}
