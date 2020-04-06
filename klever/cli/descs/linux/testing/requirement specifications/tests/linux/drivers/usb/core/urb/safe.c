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
#include <verifier/nondet.h>

static int __init ldv_init(void)
{
	int iso_packets1 = ldv_undef_int(), iso_packets2 = ldv_undef_int(), iso_packets3 = ldv_undef_int();
	gfp_t mem_flags1 = ldv_undef_uint(), mem_flags2 = ldv_undef_uint(), mem_flags3 = ldv_undef_uint();
	struct urb *urb1;
	struct urb *urb2;
	struct urb *urb3;

	urb1 = usb_alloc_urb(iso_packets1, mem_flags1);
	urb2 = usb_alloc_urb(iso_packets2, mem_flags2);
	usb_free_urb(urb1);
	usb_free_urb(urb2);

	urb3 = usb_alloc_urb(iso_packets3, mem_flags3);
	urb3 = usb_get_urb(urb3);
	usb_put_urb(urb3);
	usb_put_urb(urb3);

	return 0;
}

module_init(ldv_init);
