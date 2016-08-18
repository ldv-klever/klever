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

#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/usb.h>
#include <linux/types.h>

static int __init init(void)
{
	struct urb *tmp_1;
	struct urb *tmp_2;
	int iso_packets;
	gfp_t mem_flags;

	tmp_1 = usb_alloc_urb(iso_packets, mem_flags);
	tmp_2 = usb_alloc_urb(iso_packets, mem_flags);

	usb_free_urb(tmp_1);
	usb_free_urb(tmp_2);

	return 0;
}

module_init(init);
