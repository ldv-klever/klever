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
	struct usb_device *dev1 = ldv_undef_ptr(), *dev2 = ldv_undef_ptr();
	size_t size1 = ldv_undef_uint(), size2 = ldv_undef_uint();
	gfp_t mem_flags1 = ldv_undef_uint(), mem_flags2 = ldv_undef_uint();
	dma_addr_t dma1, dma2;
	char *buf1, *buf2;

	buf1 = usb_alloc_coherent(dev1, size1, mem_flags1, &dma1);
	buf2 = usb_alloc_coherent(dev2, size2, mem_flags2, &dma2);
	usb_free_coherent(dev1, size1, buf1, dma1);
	usb_free_coherent(dev2, size2, buf2, dma2);

	return 0;
}

module_init(ldv_init);
