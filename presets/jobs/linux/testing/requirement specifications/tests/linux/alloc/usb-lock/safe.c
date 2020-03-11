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

#include <linux/module.h>
#include <linux/usb.h>
#include <linux/gfp.h>
#include "memory.h"
#include <verifier/nondet.h>


static int __init ldv_init(void)
{
	struct usb_device *udev = ldv_undef_ptr_non_null();
	struct usb_interface *iface = ldv_undef_ptr_non_null();

	ldv_alloc(GFP_ATOMIC);
	ldv_alloc(GFP_NOIO);
	ldv_nonatomic_alloc();

	usb_lock_device(udev);
	ldv_alloc(GFP_ATOMIC);
	ldv_alloc(GFP_NOIO);
	usb_unlock_device(udev);

	if (usb_trylock_device(udev)) {
		ldv_alloc(GFP_ATOMIC);
		ldv_alloc(GFP_NOIO);
		usb_unlock_device(udev);
	}

	ldv_nonatomic_alloc();
	ldv_alloc(GFP_ATOMIC);
	ldv_nonatomic_alloc();
	ldv_alloc(GFP_NOIO);
	ldv_nonatomic_alloc();

	if (!usb_lock_device_for_reset(udev, iface)) {
		ldv_alloc(GFP_ATOMIC);
		ldv_alloc(GFP_NOIO);
		usb_unlock_device(udev);
	}

	ldv_nonatomic_alloc();
	ldv_alloc(GFP_NOIO);
	ldv_alloc(GFP_ATOMIC);

	return 0;
}

module_init(ldv_init);
