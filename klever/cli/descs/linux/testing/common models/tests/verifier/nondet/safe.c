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
#include <ldv/common/test.h>

static int __init ldv_init(void)
{
	int var1;
	long var2;
	unsigned int var3;
	unsigned long var4;
	unsigned long long var5;
	void *var6;

	var1 = ldv_undef_int();
	var2 = ldv_undef_long();
	var3 = ldv_undef_uint();
	var4 = ldv_undef_ulong();
	var5 = ldv_undef_ulonglong();
	var6 = ldv_undef_ptr();

	var1 = ldv_undef_int_positive();

	if (var1 <= 0)
		ldv_unexpected_error();

	var1 = ldv_undef_int_negative();

	if (var1 >= 0)
		ldv_unexpected_error();

	var1 = ldv_undef_int_nonnegative();

	if (var1 < 0)
		ldv_unexpected_error();

	var1 = ldv_undef_int_nonpositive();

	if (var1 > 0)
		ldv_unexpected_error();

	var1 = ldv_undef_int_range(-2, 3);

	if (var1 < -2)
		ldv_unexpected_error();

	if (var1 > 3)
		ldv_unexpected_error();

	var6 = ldv_undef_ptr_non_null();

	if (var6 == NULL)
		ldv_unexpected_error();

	return 0;
}

module_init(ldv_init);
