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

#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/usb.h>
#include <linux/vmalloc.h>

static struct my_struct
{
	const char *name;
	unsigned int *irq;
};

static int undef_int(void)
{
	int nondet;
	return nondet;
}

static void memory_allocation_nonatomic(void)
{
	int size, node;
	void *mem;
	if (undef_int()) mem = vmalloc(size);
	if (undef_int()) mem = vzalloc(size);
	if (undef_int()) mem = vmalloc_user(size);
	if (undef_int()) mem = vmalloc_node(size, node);
	if (undef_int()) mem = vzalloc_node(size, node);
	if (undef_int()) mem = vmalloc_exec(size);
	if (undef_int()) mem = vmalloc_32(size);
	if (undef_int()) mem = vmalloc_32_user(size);
}

static int __init my_init(void)
{
	struct usb_device *udev;
	usb_lock_device(udev);
	memory_allocation_nonatomic();
	usb_unlock_device(udev);
	return 0;
}

module_init(my_init);
