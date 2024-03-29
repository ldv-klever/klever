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
#include <linux/overflow.h>
#include <ldv/common/test.h>

struct ldv_struct {
	int field1;
	int field2[];
};

static int __init ldv_init(void)
{
	size_t a, b, d;
	struct ldv_struct *p;

	a = 3;
	b = 4;
	if (check_add_overflow(a, b, &d))
		ldv_unexpected_error();

	if (d != 7)
		ldv_unexpected_error();

	a = 4;
	b = 3;
	if (check_sub_overflow(a, b, &d))
		ldv_unexpected_error();

	if (d != 1)
		ldv_unexpected_error();

	a = 3;
	b = 4;
	if (check_mul_overflow(a, b, &d))
		ldv_unexpected_error();

	if (d != 12)
		ldv_unexpected_error();

	if (struct_size(p, field2, 5) != 24)
		ldv_unexpected_error();

	a = 3;
	b = 4;
	if (array_size(a, b) != 12)
		ldv_unexpected_error();

	a = 3;
	b = 4;
	d = 5;
	if (array3_size(a, b, d) != 60)
		ldv_unexpected_error();

	return 0;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
