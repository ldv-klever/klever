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
	int var1 = 1;
	ldv_list_ptr var2 = ldv_list_create(&var1);
	int var3 = 3;
	ldv_list_ptr var4;
	int var5 = 5;
	ldv_list_ptr var6;

	var4 = ldv_list_insert_data(var2, &var3);
	var6 = ldv_list_insert_data(var2, &var5);

	if (ldv_list_len(var2) == 3 &&
	    ldv_list_get_next(var2) == var6 &&
	    ldv_list_get_next(var6) == var4 &&
	    !ldv_list_get_next(var4) &&
	    ldv_list_get_last(var2) == var4 &&
	    ldv_list_get_last(var6) == var4 &&
	    ldv_list_get_last(var4) == var4 &&
	    ldv_list_get_prev(var2, var2) == var2 &&
	    ldv_list_get_prev(var2, var6) == var2 &&
	    ldv_list_get_prev(var2, var4) == var6 &&
	    *(int *)ldv_list_get_data(var2) == 1 &&
	    *(int *)ldv_list_get_data(var6) == 5 &&
	    *(int *)ldv_list_get_data(var4) == 3)
		ldv_expected_error();

	return 0;
}

module_init(ldv_init);
