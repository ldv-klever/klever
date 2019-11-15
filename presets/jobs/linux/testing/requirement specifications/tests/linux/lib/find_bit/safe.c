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
#include <asm-generic/bitops/find.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

static int __init ldv_init(void)
{
	unsigned long size = ldv_undef_ulong(), offset = ldv_undef_ulong();
	const unsigned long *addr = ldv_undef_ptr();

	ldv_assume(size >= offset);
	find_next_zero_bit(addr, size, offset);
	find_next_bit(addr, size, offset);

	return 0;
}

module_init(ldv_init);
