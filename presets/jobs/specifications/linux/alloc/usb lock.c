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

#include <linux/gfp.h>
#include <ldv/linux/slab.h>
#include <ldv/verifier/common.h>
#include <ldv/verifier/nondet.h>

/* NOTE USB lock is not acquired at the beginning */
int ldv_lock = 1;

void ldv_check_alloc_flags(gfp_t flags)
{
	if (ldv_lock == 2 && flags != GFP_NOIO && flags != GFP_ATOMIC)
		/* ASSERT GFP_NOIO or GFP_ATOMIC flag should be used when USB lock is acquired */
		ldv_assert();
}

void ldv_check_alloc_nonatomic(void)
{
	if (ldv_lock != 1)
		/* ASSERT USB lock should not be acquired */
		ldv_assert();
}

void ldv_usb_lock_device(void)
{
	/* NOTE Acquire USB lock */
	ldv_lock = 2;
}

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

void ldv_usb_unlock_device(void)
{
	/* NOTE Release USB lock */
	ldv_lock = 1;
}
