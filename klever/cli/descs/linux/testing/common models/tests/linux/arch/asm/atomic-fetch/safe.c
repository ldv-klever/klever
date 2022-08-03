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
#include <linux/atomic.h>
#include <ldv/common/test.h>

static int __init ldv_init(void)
{
	atomic_t v;

	atomic_set(&v, 0);

	if (atomic_fetch_add(2, &v) != 0)
		ldv_unexpected_error();

	if (atomic_fetch_add(3, &v) != 2)
		ldv_unexpected_error();

	if (atomic_fetch_sub(2, &v) != 5)
		ldv_unexpected_error();

	if (atomic_fetch_sub(3, &v) != 3)
		ldv_unexpected_error();

	if (atomic_read(&v) != 0)
		ldv_unexpected_error();

	return 0;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
