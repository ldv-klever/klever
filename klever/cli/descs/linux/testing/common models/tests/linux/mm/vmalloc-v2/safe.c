/*
 * Copyright (c) 2021 ISP RAS (http://www.ispras.ru)
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
#include <linux/vmalloc.h>
#include <ldv/common/test.h>

static bool is_check_invoked;

void ldv_check_alloc_nonatomic(void)
{
	is_check_invoked = true;
}

static int __init ldv_init(void)
{
	void *p;
	size_t size = ldv_undef_uint();
	int node = ldv_undef_int();

	p = vmalloc(size);

	if (!is_check_invoked)
		ldv_unexpected_error();

	is_check_invoked = false;
	p = vzalloc(size);

	if (!is_check_invoked)
		ldv_unexpected_error();

	is_check_invoked = false;
	p = vmalloc_user(size);

	if (!is_check_invoked)
		ldv_unexpected_error();

	is_check_invoked = false;
	p = vmalloc_node(size, node);

	if (!is_check_invoked)
		ldv_unexpected_error();

	is_check_invoked = false;
	p = vzalloc_node(size, node);

	if (!is_check_invoked)
		ldv_unexpected_error();

	is_check_invoked = false;
	p = vmalloc_32(size);

	if (!is_check_invoked)
		ldv_unexpected_error();

	is_check_invoked = false;
	p = vmalloc_32_user(size);

	if (!is_check_invoked)
		ldv_unexpected_error();

	return 0;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
