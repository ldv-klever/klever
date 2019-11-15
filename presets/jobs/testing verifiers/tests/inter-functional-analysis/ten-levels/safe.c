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
#include "funcs.h"

static int __init ldv_init(void)
{
	int var1 = ldv_undef_int(), var2 = ldv_undef_int(),
	    var3 = ldv_undef_int(), var4 = ldv_undef_int(),
	    var5 = ldv_undef_int(), var6 = ldv_undef_int(),
	    var7 = ldv_undef_int(), var8 = ldv_undef_int(),
	    var9 = ldv_undef_int(), var10 = ldv_undef_int();

	if (ldv_func1(var1) != var1)
		ldv_unexpected_error();

	if (ldv_func2(var2) != -var2)
		ldv_unexpected_error();

	if (ldv_func3(var3) != var3)
		ldv_unexpected_error();

	if (ldv_func4(var4) != -var4)
		ldv_unexpected_error();

	if (ldv_func5(var5) != var5)
		ldv_unexpected_error();

	if (ldv_func6(var6) != -var6)
		ldv_unexpected_error();

	if (ldv_func7(var7) != var7)
		ldv_unexpected_error();

	if (ldv_func8(var8) != -var8)
		ldv_unexpected_error();

	if (ldv_func9(var9) != var9)
		ldv_unexpected_error();

	if (ldv_func10(var10) != -var10)
		ldv_unexpected_error();

	return 0;
}

module_init(ldv_init);
