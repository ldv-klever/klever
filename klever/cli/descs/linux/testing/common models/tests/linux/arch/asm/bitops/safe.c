/*
 * Copyright (c) 2022 ISP RAS (http://www.ispras.ru)
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
#include <linux/bitops.h>
#include <ldv/common/test.h>

#define LDV_BIT_MAX 0x100
static DECLARE_BITMAP(ldv_bitmap, LDV_BIT_MAX);

static int __init ldv_init(void)
{
	unsigned long bit, counter;

	set_bit(1, ldv_bitmap);

	if (!test_bit(1, ldv_bitmap))
		ldv_unexpected_memory_safety_error();

	set_bit(10, ldv_bitmap);

	if (!test_bit(10, ldv_bitmap))
		ldv_unexpected_memory_safety_error();

	set_bit(100, ldv_bitmap);

	if (!test_bit(100, ldv_bitmap))
		ldv_unexpected_memory_safety_error();

	clear_bit(10, ldv_bitmap);

	if (test_bit(10, ldv_bitmap))
		ldv_unexpected_memory_safety_error();

	counter = 0;
	for_each_set_bit(bit, ldv_bitmap, LDV_BIT_MAX) {
		clear_bit(bit, ldv_bitmap);
		counter++;
	}

	if (counter != 2)
		ldv_unexpected_memory_safety_error();

	if (find_next_bit(ldv_bitmap, LDV_BIT_MAX, 0) != LDV_BIT_MAX)
		ldv_unexpected_memory_safety_error();

	return 0;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
