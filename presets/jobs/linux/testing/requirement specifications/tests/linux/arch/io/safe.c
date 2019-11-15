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
#include <asm/io.h>
#include <verifier/nondet.h>

static int __init ldv_init(void)
{
	phys_addr_t offset = ldv_undef_uint();
	unsigned long size = ldv_undef_ulong();
	void *io_base;

	io_base = ioremap(offset, size);
	if (!io_base)
		return ldv_undef_int_negative();

	iounmap(io_base);

	return 0;
}

module_init(ldv_init);
