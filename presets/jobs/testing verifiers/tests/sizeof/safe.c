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
#include <ldv/test.h>

struct ldv_struct1 {
	char field;
};

struct ldv_struct2 {
	char field1;
	int field2;
};

struct ldv_struct3 {
	int field1;
	int field2;
};

static int __init ldv_init(void)
{
	int var1, *var2;
	struct ldv_struct1 var3, *var4;

	if (sizeof(char) != 1)
		ldv_unexpected_error();

	if (sizeof(short int) != 2)
		ldv_unexpected_error();

	if (sizeof(int) != 4)
		ldv_unexpected_error();

	if (sizeof(long int) != 8)
		ldv_unexpected_error();

	if (sizeof(long long int) != 8)
		ldv_unexpected_error();

	if (sizeof(void *) != 8)
		ldv_unexpected_error();

	if (sizeof(struct ldv_struct1) != 1)
		ldv_unexpected_error();

	if (sizeof(struct ldv_struct2) != 8)
		ldv_unexpected_error();

	if (sizeof(struct ldv_struct3) != 8)
		ldv_unexpected_error();

	if (sizeof(var1) != 4)
		ldv_unexpected_error();

	if (sizeof(var2) != 8)
		ldv_unexpected_error();

	if (sizeof(var3) != 1)
		ldv_unexpected_error();

	if (sizeof(var4) != 8)
		ldv_unexpected_error();

	return 0;
}

module_init(ldv_init);
