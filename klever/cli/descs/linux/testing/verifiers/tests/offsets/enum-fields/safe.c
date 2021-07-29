/*
 * Copyright (c) 2021 ISP RAS (http://www.ispras.ru)
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

enum ldv_enum1 {
	ldv_enumerator11,
	ldv_enumerator12,
	ldv_enumerator13
};

enum ldv_enum2 {
	ldv_enumerator21,
	ldv_enumerator22
};

struct ldv_struct1 {
	char field1;
	char field11;
	char field12;
	char field13;
	enum ldv_enum1 field2;
	enum ldv_enum2 field3;
	int field4;
};

static int __init ldv_init(void)
{
	struct ldv_struct1 var1 = {1, 0, 0, 0, ldv_enumerator11, ldv_enumerator21, 2}, var2, *var3, *var4;

	if (var1.field1 != 1)
		ldv_unexpected_error();

	if (var1.field2 != ldv_enumerator11)
		ldv_unexpected_error();

	if (var1.field3 != ldv_enumerator21)
		ldv_unexpected_error();

	if (var1.field4 != 2)
		ldv_unexpected_error();

	var2.field1 = 3;
	var2.field2 = ldv_enumerator12;
	var2.field3 = ldv_enumerator22;
	var2.field4 = 4;

	if (var2.field1 != 3)
		ldv_unexpected_error();

	if (var2.field2 != ldv_enumerator12)
		ldv_unexpected_error();

	if (var2.field3 != ldv_enumerator22)
		ldv_unexpected_error();

	if (var2.field4 != 4)
		ldv_unexpected_error();

	var3 = ldv_xmalloc(sizeof(*var3));
	var3->field1 = 5;
	var3->field2 = ldv_enumerator13;
	var3->field3 = ldv_enumerator21;
	var3->field4 = 6;

	if (var3->field1 != 5)
		ldv_unexpected_error();

	if (var3->field2 != ldv_enumerator13)
		ldv_unexpected_error();

	if (var3->field3 != ldv_enumerator21)
		ldv_unexpected_error();

	if (var3->field4 != 6)
		ldv_unexpected_error();

	ldv_free(var3);

	var4 = ldv_xcalloc(2, sizeof(*var4));
	var4->field1 = 7;
	var4->field2 = ldv_enumerator11;
	var4->field3 = ldv_enumerator22;
	var4->field4 = 8;
	(var4 + 1)->field1 = 9;
	(var4 + 1)->field2 = ldv_enumerator12;
	(var4 + 1)->field3 = ldv_enumerator21;
	(var4 + 1)->field4 = 10;

	if (var4->field1 != 7)
		ldv_unexpected_error();

	if (var4->field2 != ldv_enumerator11)
		ldv_unexpected_error();

	if (var4->field3 != ldv_enumerator22)
		ldv_unexpected_error();

	if (var4->field4 != 8)
		ldv_unexpected_error();

	if ((var4 + 1)->field1 != 9)
		ldv_unexpected_error();

	if ((var4 + 1)->field2 != ldv_enumerator12)
		ldv_unexpected_error();

	if ((var4 + 1)->field3 != ldv_enumerator21)
		ldv_unexpected_error();

	if ((var4 + 1)->field4 != 10)
		ldv_unexpected_error();

	ldv_free(var4);

	return 0;
}

module_init(ldv_init);
