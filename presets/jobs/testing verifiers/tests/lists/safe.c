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
#include "lists.h"

static int __init ldv_init(void)
{
	int var1 = ldv_undef_int();
	ldv_list_ptr var2 = ldv_list_create(&var1);
	int var3 = ldv_undef_int();
	ldv_list_ptr var4;
	int var5 = ldv_undef_int();
	ldv_list_ptr var6;
	ldv_list_ptr var7;

	if (ldv_list_len(var2) != 1)
		ldv_unexpected_error();

	if (ldv_list_get_next(var2))
		ldv_unexpected_error();

	if (ldv_list_get_last(var2) != var2)
		ldv_unexpected_error();

	if (ldv_list_get_prev(var2, var2) != var2)
		ldv_unexpected_error();

	if (*(int *)ldv_list_get_data(var2) != var1)
		ldv_unexpected_error();

	var4 = ldv_list_insert_data(var2, &var3);

	if (ldv_list_len(var2) != 2)
		ldv_unexpected_error();

	if (ldv_list_get_next(var2) != var4)
		ldv_unexpected_error();

	if (ldv_list_get_next(var4))
		ldv_unexpected_error();

	if (ldv_list_get_last(var2) != var4)
		ldv_unexpected_error();

	if (ldv_list_get_last(var4) != var4)
		ldv_unexpected_error();

	if (ldv_list_get_prev(var2, var2) != var2)
		ldv_unexpected_error();

	if (ldv_list_get_prev(var2, var4) != var2)
		ldv_unexpected_error();

	if (*(int *)ldv_list_get_data(var2) != var1)
		ldv_unexpected_error();

	if (*(int *)ldv_list_get_data(var4) != var3)
		ldv_unexpected_error();

	var6 = ldv_list_insert_data(var2, &var5);

	if (ldv_list_len(var2) != 3)
		ldv_unexpected_error();

	if (ldv_list_get_next(var2) != var6)
		ldv_unexpected_error();

	if (ldv_list_get_next(var6) != var4)
		ldv_unexpected_error();

	if (ldv_list_get_next(var4))
		ldv_unexpected_error();

	if (ldv_list_get_last(var2) != var4)
		ldv_unexpected_error();

	if (ldv_list_get_last(var6) != var4)
		ldv_unexpected_error();

	if (ldv_list_get_last(var4) != var4)
		ldv_unexpected_error();

	if (ldv_list_get_prev(var2, var2) != var2)
		ldv_unexpected_error();

	if (ldv_list_get_prev(var2, var6) != var2)
		ldv_unexpected_error();

	if (ldv_list_get_prev(var2, var4) != var6)
		ldv_unexpected_error();

	if (*(int *)ldv_list_get_data(var2) != var1)
		ldv_unexpected_error();

	if (*(int *)ldv_list_get_data(var6) != var5)
		ldv_unexpected_error();

	if (*(int *)ldv_list_get_data(var4) != var3)
		ldv_unexpected_error();

	var7 = ldv_list_delete(&var2, var6);

	if (var7 != var2)
		ldv_unexpected_error();

	if (ldv_list_len(var2) != 2)
		ldv_unexpected_error();

	if (ldv_list_get_next(var2) != var4)
		ldv_unexpected_error();

	if (ldv_list_get_next(var4))
		ldv_unexpected_error();

	if (ldv_list_get_last(var2) != var4)
		ldv_unexpected_error();

	if (ldv_list_get_last(var4) != var4)
		ldv_unexpected_error();

	if (ldv_list_get_prev(var2, var2) != var2)
		ldv_unexpected_error();

	if (ldv_list_get_prev(var2, var4) != var2)
		ldv_unexpected_error();

	if (*(int *)ldv_list_get_data(var2) != var1)
		ldv_unexpected_error();

	if (*(int *)ldv_list_get_data(var4) != var3)
		ldv_unexpected_error();

	ldv_list_delete_all(var2);

	return 0;
}

module_init(ldv_init);
