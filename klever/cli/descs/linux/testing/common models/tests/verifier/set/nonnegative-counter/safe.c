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
#include "sets-model.h"

static int __init ldv_init(void)
{
	ldv_set set;

	/*
	 * Ignoring elements and using nonnegative counter as sets model behaves
	 * like counter sets model except it forbids to remove unexisting elements
	 * from empty sets.
	 */
	ldv_set_init(set);

	if (!ldv_set_is_empty(set))
		ldv_unexpected_error();

	if (ldv_set_contains(set, element))
		ldv_unexpected_error();

	ldv_set_add(set, element);

	if (ldv_set_is_empty(set))
		ldv_unexpected_error();

	if (!ldv_set_contains(set, element))
		ldv_unexpected_error();

	ldv_set_remove(set, element);

	if (!ldv_set_is_empty(set))
		ldv_unexpected_error();

	if (ldv_set_contains(set, element))
		ldv_unexpected_error();

	ldv_set_remove(set, element);

	if (!ldv_set_is_empty(set))
		ldv_unexpected_error();

	if (ldv_set_contains(set, element))
		ldv_unexpected_error();

	ldv_set_add(set, element1);
	ldv_set_add(set, element2);

	if (ldv_set_is_empty(set))
		ldv_unexpected_error();

	if (!ldv_set_contains(set, element1))
		ldv_unexpected_error();

	if (!ldv_set_contains(set, element1))
		ldv_unexpected_error();

	ldv_set_remove(set, element1);

	if (ldv_set_is_empty(set))
		ldv_unexpected_error();

	if (!ldv_set_contains(set, element2))
		ldv_unexpected_error();

	ldv_set_remove(set, element2);

	if (!ldv_set_is_empty(set))
		ldv_unexpected_error();

	if (ldv_set_contains(set, element1))
		ldv_unexpected_error();

	if (ldv_set_contains(set, element2))
		ldv_unexpected_error();

	return 0;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
