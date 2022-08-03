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
#include <linux/list.h>
#include <ldv/common/test.h>

static LIST_HEAD(ldv_list);

struct ldv_struct
{
	int field;
	struct list_head list;
};

static int __init ldv_init(void)
{
	struct ldv_struct var1 = {.field = 1}, var2 = {.field = 2}, var3 = {.field = 3}, *p_var;
	int i;

	if (!list_empty(&ldv_list))
		ldv_unexpected_memory_safety_error();

	list_add_tail(&var1.list, &ldv_list);
	list_add_tail(&var2.list, &ldv_list);
	list_add_tail(&var3.list, &ldv_list);

	i = 0;
	list_for_each_entry(p_var, &ldv_list, list) {
		if (i == 0) {
			if (p_var->field != 1)
				ldv_unexpected_memory_safety_error();
		} else if (i == 1) {
			if (p_var->field != 2)
				ldv_unexpected_memory_safety_error();
		} else if (i == 2) {
			if (p_var->field != 3)
				ldv_unexpected_memory_safety_error();
		} else
			ldv_unexpected_memory_safety_error();

		i++;
	}

	list_del(&var2.list);
	i = 0;
	list_for_each_entry(p_var, &ldv_list, list) {
		if (i == 0) {
			if (p_var->field != 1)
				ldv_unexpected_memory_safety_error();
		} else if (i == 1) {
			if (p_var->field != 3)
				ldv_unexpected_memory_safety_error();
		} else
			ldv_unexpected_memory_safety_error();

		i++;
	}

	list_del(&var1.list);
	list_del(&var3.list);

	if (!list_empty(&ldv_list))
		ldv_unexpected_memory_safety_error();

	list_add(&var1.list, &ldv_list);
	list_add(&var2.list, &ldv_list);
	list_add(&var3.list, &ldv_list);

	i = 0;
	list_for_each_entry(p_var, &ldv_list, list) {
		if (i == 0) {
			if (p_var->field != 3)
				ldv_unexpected_memory_safety_error();
		} else if (i == 1) {
			if (p_var->field != 2)
				ldv_unexpected_memory_safety_error();
		} else if (i == 2) {
			if (p_var->field != 1)
				ldv_unexpected_memory_safety_error();
		} else
			ldv_unexpected_memory_safety_error();

		i++;
	}

	return 0;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
