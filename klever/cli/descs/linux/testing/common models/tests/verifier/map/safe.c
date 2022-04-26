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
	ldv_map map;
	ldv_map_value value1 = 1, value2 = 2;

	/*
	 * Maps model ignoring keys is extremely restricted since it allows to.
	 * safely represent just maps containing single key.
	 */
	ldv_map_init(map);

	if (!ldv_map_is_empty(map))
		ldv_unexpected_error();

	if (ldv_map_contains_key(map, key))
		ldv_unexpected_error();

	if (ldv_map_get(map, key))
		ldv_unexpected_error();

	ldv_map_put(map, key, value1);

	if (ldv_map_is_empty(map))
		ldv_unexpected_error();

	if (!ldv_map_contains_key(map, key))
		ldv_unexpected_error();

	if (ldv_map_get(map, key) != value1)
		ldv_unexpected_error();

	ldv_map_put(map, key, value2);

	if (ldv_map_is_empty(map))
		ldv_unexpected_error();

	if (!ldv_map_contains_key(map, key))
		ldv_unexpected_error();

	if (ldv_map_get(map, key) != value2)
		ldv_unexpected_error();

	ldv_map_remove(map, key);

	if (!ldv_map_is_empty(map))
		ldv_unexpected_error();

	if (ldv_map_contains_key(map, key))
		ldv_unexpected_error();

	if (ldv_map_get(map, key))
		ldv_unexpected_error();

	return 0;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
