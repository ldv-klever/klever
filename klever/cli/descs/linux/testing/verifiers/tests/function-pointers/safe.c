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
#include "func.h"

static int __init ldv_init(void)
{
	ldv_func_t var1 = ldv_func1, var2 = ldv_func2;
	int var3 = ldv_undef_int(), var4 = ldv_undef_int();
	ldv_func_t var5[2] = {ldv_func1, ldv_func2};
	struct ldv_struct var6 = {ldv_func1, ldv_func2};

	if (var1(var3) != var3)
		ldv_unexpected_error();

	if (var2(var4) != -var4)
		ldv_unexpected_error();

	if (var5[0](var3) != var3)
		ldv_unexpected_error();

	if (var5[1](var4) != -var4)
		ldv_unexpected_error();

	if (var6.field1(var3) != var3)
		ldv_unexpected_error();

	if (var6.field2(var4) != -var4)
		ldv_unexpected_error();

	return 0;
}

module_init(ldv_init);
