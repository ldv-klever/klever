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
#include <linux/device.h>
#include <linux/fs.h>
#include <linux/usb/gadget.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

static int __init ldv_init(void)
{
	struct usb_gadget_driver driver;
	struct class class;
	dev_t dev = ldv_undef_uint();
	unsigned int baseminor = ldv_undef_uint(), count = ldv_undef_uint();
	const char *name = ldv_undef_ptr();

	ldv_assume(!IS_ERR(&class));

	if (!usb_gadget_probe_driver(&driver))
		usb_gadget_unregister_driver(&driver);

	if (!class_register(&class)) {
		if (!alloc_chrdev_region(&dev, baseminor, count, name)) {
			if (!usb_gadget_probe_driver(&driver))
				usb_gadget_unregister_driver(&driver);
			unregister_chrdev_region(dev, count);
		}
		class_destroy(&class);
	}

	return 0;
}

module_init(ldv_init);
