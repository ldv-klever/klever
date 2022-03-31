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
	if (flags != ldv_flags)
		ldv_unexpected_error();
}

static int __init ldv_init(void)
{
	size_t size = ldv_undef_uint();
	size_t n = ldv_undef_uint();
	struct kmem_cache *cachep;

	ldv_flags = ldv_undef_uint();

	kmalloc(size, ldv_flags);
	kzalloc(size, ldv_flags);
	kmalloc_array(n, size, ldv_flags);
	kcalloc(n, size, ldv_flags);

	cachep = kmem_cache_create("ldv", sizeof(struct ldv_struct1), 0, 0, NULL);
	ldv_assume(cachep != NULL);
	kmem_cache_alloc(cachep, ldv_flags);
	kmem_cache_zalloc(cachep, ldv_flags);

	return 0;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
