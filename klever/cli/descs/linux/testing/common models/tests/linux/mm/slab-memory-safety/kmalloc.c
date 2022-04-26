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
#include <linux/slab.h>
#include <ldv/common/test.h>
#include "../slab.h"

gfp_t ldv_flags;

void ldv_check_alloc_flags(gfp_t flags)
{
	if (flags == ldv_flags)
		ldv_expected_error();
}

static int __init ldv_init(void)
{
	size_t size = sizeof(struct ldv_struct1);

	ldv_flags = GFP_KERNEL;
	kmalloc(size, ldv_flags);

	return 0;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
