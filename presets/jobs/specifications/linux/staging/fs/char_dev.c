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

#include <linux/ldv/common.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

/* There are 2 possible states of char device region registration. */
enum
{
	LDV_CHRDEV_ZERO_STATE, /* Char device region is not registered for usb gadget. */
	LDV_CHRDEV_REGISTERED  /* Char device region is registered for usb gadget. */
};

/* NOTE Char device region is not registered at the beginning */
int ldv_usb_gadget_chrdev = LDV_CHRDEV_ZERO_STATE;

/* MODEL_FUNC Check that chrdev region was not registered and register it */
int ldv_register_chrdev(int major)
{
	int is_reg;

	/* NOTE Register chrdev in the nondeterministic way */
	is_reg = ldv_undef_int_nonpositive();

	/* ASSERT Register chrdev just in case when an error did not happen */
	if (!is_reg) {
		/* ASSERT Check that chrdev region is unregistered */
		ldv_assert("linux:fs:char_dev::double registration", ldv_usb_gadget_chrdev == LDV_CHRDEV_ZERO_STATE);
		/* NOTE Register chrdev region for usb gadget */
		ldv_usb_gadget_chrdev = LDV_CHRDEV_REGISTERED;
		if (major == 0) {
			/* NOTE Function returns allocated major number */
			is_reg = ldv_undef_int();
			ldv_assume (is_reg > 0);
		}
	}

	/* NOTE Return registration status (0 is success) */
	return is_reg;
}

/* MODEL_FUNC Check that chrdev region was not registered and register it */
int ldv_register_chrdev_region(void)
{
	int is_reg;

	/* NOTE Register chrdev in the nondeterministic way */
	is_reg = ldv_undef_int_nonpositive();

	/* ASSERT Register chrdev just in case when an error did not happen */
	if (!is_reg) {
		/* ASSERT Check that chrdev region is unregistered */
		ldv_assert("linux:fs:char_dev::double registration", ldv_usb_gadget_chrdev == LDV_CHRDEV_ZERO_STATE);
		/* NOTE Register chrdev region for usb gadget */
		ldv_usb_gadget_chrdev = LDV_CHRDEV_REGISTERED;
	}

	/* NOTE Return registration status (0 is success) */
	return is_reg;
}

/* MODEL_FUNC Check that chrdev region was registered and unregister it */
void ldv_unregister_chrdev_region(void)
{
	/* ASSERT Check that chrdev region is registered */
	ldv_assert("linux:fs:char_dev::double deregistration", ldv_usb_gadget_chrdev == LDV_CHRDEV_REGISTERED);
	/* NOTE Unregister chrdev */
	ldv_usb_gadget_chrdev = LDV_CHRDEV_ZERO_STATE;
}

/* MODEL_FUNC Check that usb gadget is fully unregistered at the end */
void ldv_check_final_state(void)
{
	/* ASSERT Chrdev region should be unregistered at the end */
	ldv_assert("linux:fs:char_dev::registered at exit", ldv_usb_gadget_chrdev == LDV_CHRDEV_ZERO_STATE);
}
