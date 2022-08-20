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
	size_t size = sizeof(struct ldv_struct1);
	size_t n = 5;
	void *res;
	struct kmem_cache *cachep1, *cachep2, *cachep3;

	ldv_flags = GFP_KERNEL;

	res = kmalloc(size, ldv_flags);
	if (res)
		kfree(res);
	res = kzalloc(size, ldv_flags);
	if (res)
		kfree(res);
	res = kmalloc_array(n, size, ldv_flags);
	if (res)
		kfree(res);
	res = kcalloc(n, size, ldv_flags);
	if (res)
		kfree(res);

	cachep1 = kmem_cache_create("ldv1", sizeof(struct ldv_struct1), 0, 0, NULL);
	if (!cachep1)
		return -1;
	res = kmem_cache_alloc(cachep1, ldv_flags);
	if (res)
		kmem_cache_free(cachep1, res);
	res = kmem_cache_zalloc(cachep1, ldv_flags);
	if (res)
		kmem_cache_free(cachep1, res);
	kmem_cache_destroy(cachep1);

	cachep2 = kmem_cache_create("ldv2", sizeof(struct ldv_struct2), 0, 0, NULL);
	if (!cachep2)
		return -1;
	cachep3 = kmem_cache_create("ldv3", sizeof(struct ldv_struct3), 0, 0, NULL);
	if (!cachep3) {
		kmem_cache_destroy(cachep2);
		return -1;
	}
	res = kmem_cache_alloc(cachep2, ldv_flags);
	if (res)
		kmem_cache_free(cachep2, res);
	res = kmem_cache_alloc(cachep3, ldv_flags);
	if (res)
		kmem_cache_free(cachep3, res);
	kmem_cache_destroy(cachep2);
	kmem_cache_destroy(cachep3);

	res = kmalloc(SIZE_MAX, ldv_flags);
	if (res)
		ldv_unexpected_error();
	res = kzalloc(SIZE_MAX, ldv_flags);
	if (res)
		ldv_unexpected_error();
	res = kcalloc(n, SIZE_MAX, ldv_flags);
	if (res)
		ldv_unexpected_error();

	res = ldv_xmalloc(SIZE_MAX);
	if (res)
		ldv_unexpected_error();
	res = ldv_xzalloc(SIZE_MAX);
	if (res)
		ldv_unexpected_error();
	res = ldv_xcalloc(n, SIZE_MAX);
	if (res)
		ldv_unexpected_error();

	return 0;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
