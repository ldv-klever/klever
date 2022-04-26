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

	if (atomic_read(&v) != 0)
		ldv_unexpected_error();

	atomic_add(5, &v);

	if (atomic_read(&v) != 5)
		ldv_unexpected_error();

	atomic_sub(5, &v);

	if (atomic_read(&v) != 0)
		ldv_unexpected_error();

	atomic_set(&v, 3);

	if (atomic_sub_and_test(1, &v) != 0)
		ldv_unexpected_error();

	if (atomic_sub_and_test(2, &v) != 1)
		ldv_unexpected_error();

	atomic_inc(&v);

	if (atomic_read(&v) != 1)
		ldv_unexpected_error();

	atomic_dec(&v);

	if (atomic_read(&v) != 0)
		ldv_unexpected_error();

	if (atomic_dec_and_test(&v) != 0)
		ldv_unexpected_error();

	if (atomic_inc_and_test(&v) != 1)
		ldv_unexpected_error();

	if (atomic_inc_and_test(&v) != 0)
		ldv_unexpected_error();

	if (atomic_dec_and_test(&v) != 1)
		ldv_unexpected_error();

	if (atomic_add_return(5, &v) != 5)
		ldv_unexpected_error();

	if (atomic_add_negative(-3, &v) != 0)
		ldv_unexpected_error();

	if (atomic_add_negative(-3, &v) != 1)
		ldv_unexpected_error();

	return 0;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
