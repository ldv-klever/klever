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

/* There are 2 possible states of usb gadget registration. */
enum
{
	LDV_USB_GADGET_ZERO_STATE, /* Usb gadget is not registered. */
	LDV_USB_GADGET_REGISTERED  /* Usb gadget is registered. */
};

/* NOTE Usb gadget is not registered at the beginning */
int ldv_usb_gadget = LDV_USB_GADGET_ZERO_STATE;


void *ldv_create_class(void)
{
	void *is_got;

	/* NOTE Get blk request in the nondeterministic way */
	is_got = ldv_undef_ptr();

	/* NOTE Function cannot return NULL */
	ldv_assume(is_got);

	if (!ldv_is_err(is_got) && ldv_usb_gadget != LDV_USB_GADGET_ZERO_STATE)
		/* ASSERT Registering usb gadget class is only allowed if usb gadget is not registered */
		ldv_assert();

	/* NOTE Return obtained blk request */
	return is_got;
}

int ldv_register_class(void)
{
	int is_reg;

	/* NOTE Register gadget class in the nondeterministic way */
	is_reg = ldv_undef_int_nonpositive();

	if (!is_reg && ldv_usb_gadget != LDV_USB_GADGET_ZERO_STATE)
		/* ASSERT Registering usb gadget class is only allowed if usb gadget is not registered */
		ldv_assert();

	/* NOTE Return registration status (0 is success) */
	return is_reg;
}

void ldv_unregister_class(void)
{
	if (ldv_usb_gadget != LDV_USB_GADGET_ZERO_STATE)
		/* ASSERT Unregistering usb gadget class is only allowed if usb gadget is not registered */
		ldv_assert();
}

void ldv_destroy_class(struct class *cls)
{
    if ((cls == 0) || (ldv_is_err(cls)))
        return;
    ldv_unregister_class();
}

int ldv_register_chrdev(int major)
{
	int is_reg;

	/* NOTE Register chrdev in the nondeterministic way */
	is_reg = ldv_undef_int_nonpositive();

	if (!is_reg) {
		if (ldv_usb_gadget != LDV_USB_GADGET_ZERO_STATE)
			/* ASSERT Usb gadget should be unregistered at this point */
			ldv_assert();

		if (major == 0) {
			/* NOTE Function returns allocated major number */
			is_reg = ldv_undef_int();
			ldv_assume(is_reg > 0);
		}
	}

	/* NOTE Return registration status (0 is success) */
	return is_reg;
}

int ldv_register_chrdev_region(void)
{
	int is_reg;

	/* NOTE Register chrdev in the nondeterministic way */
	is_reg = ldv_undef_int_nonpositive();

	if (!is_reg && ldv_usb_gadget != LDV_USB_GADGET_ZERO_STATE)
		/* ASSERT Usb gadget should be unregistered at this point */
		ldv_assert();

	/* NOTE Return registration status (0 is success) */
	return is_reg;
}

void ldv_unregister_chrdev_region(void)
{
	if (ldv_usb_gadget != LDV_USB_GADGET_ZERO_STATE)
		/* ASSERT Usb gadget should not be registered at this point */
		ldv_assert();
}

int ldv_register_usb_gadget(void)
{
	int is_reg;

	/* NOTE Register usb gadget in the nondeterministic way */
	is_reg = ldv_undef_int_nonpositive();

	if (!is_reg) {
		if (ldv_usb_gadget != LDV_USB_GADGET_ZERO_STATE)
			/* ASSERT Gadget should not be registered at this point */
			ldv_assert();

		/* NOTE Register usb gadget */
		ldv_usb_gadget = LDV_USB_GADGET_REGISTERED;
	}

	/* NOTE Return registration status (0 is success) */
	return is_reg;
}

void ldv_unregister_usb_gadget(void)
{
	if (ldv_usb_gadget != LDV_USB_GADGET_REGISTERED)
		/* ASSERT Usb gadget should be registered at this point */
		ldv_assert();

	/* NOTE Unregister usb gadget */
	ldv_usb_gadget = LDV_USB_GADGET_ZERO_STATE;
}

void ldv_check_final_state(void)
{
	if (ldv_usb_gadget != LDV_USB_GADGET_ZERO_STATE)
		/* ASSERT Usb gadget should be unregistered at the end */
		ldv_assert();
}
