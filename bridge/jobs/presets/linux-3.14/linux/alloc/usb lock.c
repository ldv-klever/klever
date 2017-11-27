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

#include <linux/gfp.h>
#include <linux/ldv/slab.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

/* NOTE USB lock is not acquired at the beginning */
int ldv_lock = 1;

/* MODEL_FUNC Check that correct flag was used when USB lock is aquired */
void ldv_check_alloc_flags(gfp_t flags) 
{
	if (ldv_lock == 2)
	{
		/* ASSERT GFP_NOIO or GFP_ATOMIC flag should be used when USB lock is aquired */
		ldv_assert("linux:alloc:usb lock::wrong flags", flags == GFP_NOIO || flags == GFP_ATOMIC);
	}
}

/* MODEL_FUNC Check that USB lock is not acquired */
void ldv_check_alloc_nonatomic(void)
{
	/* ASSERT USB lock should not be acquired */
	ldv_assert("linux:alloc:usb lock::nonatomic", ldv_lock == 1);
}

/* MODEL_FUNC Acquire USB lock */
void ldv_usb_lock_device(void)
{
	/* NOTE Acquire USB lock */
	ldv_lock = 2;
}

/* MODEL_FUNC Try to acquire USB lock */
int ldv_usb_trylock_device(void)
{
	if (ldv_lock == 1 && ldv_undef_int())
	{
		/* NOTE Acquire USB lock */
		ldv_lock = 2;
		/* NOTE USB lock was acquired */
		return 1;
	}
	else
	{
		/* NOTE USB lock was not acquired */
		return 0;
	}
}

/* MODEL_FUNC Try to acquire USB lock */
int ldv_usb_lock_device_for_reset(void)
{
	if (ldv_lock == 1 && ldv_undef_int())
	{
		/* NOTE Acquire USB lock */
		ldv_lock = 2;
		/* NOTE USB lock was acquired */
		return 0;
	}
	else
	{
		/* NOTE USB lock wad not acquired */
		return -1;
	}
}

/* MODEL_FUNC Release USB lock */
void ldv_usb_unlock_device(void)
{
	/* NOTE Release USB lock */
	ldv_lock = 1;
}
