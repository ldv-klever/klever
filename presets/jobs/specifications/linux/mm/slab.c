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

#include <linux/types.h>
#include <linux/slab.h>
#include <ldv/linux/common.h>
#include <ldv/linux/slab.h>
#include <ldv/verifier/memory.h>

void *ldv_kmalloc(size_t size, gfp_t flags)
{
	void *res;

	ldv_check_alloc_flags(flags);
	res = ldv_malloc(size);

	return res;
}

void *ldv_kzalloc(size_t size, gfp_t flags)
{
	void *res;

	ldv_check_alloc_flags(flags);
	res = ldv_zalloc(size);

	return res;
}

void *ldv_kmalloc_array(size_t n, size_t size, gfp_t flags)
{
	void *res;

	ldv_check_alloc_flags(flags);
	res = ldv_malloc(n * size);

	return res;
}

void *ldv_kcalloc(size_t n, size_t size, gfp_t flags)
{
	void *res;

	ldv_check_alloc_flags(flags);
	res = ldv_calloc(n, size);

	return res;
}

struct kmem_cache *ldv_kmem_cache_create(const char *name, unsigned int size)
{
	struct kmem_cache *res;

	res = ldv_zalloc(sizeof(*res));

	if (res) {
		res->name = name;
		res->size = size;
		res->object_size = size;
	}

	return res;
}

void *ldv_kmem_cache_alloc(struct kmem_cache *cachep, gfp_t flags)
{
	return ldv_kmalloc(cachep->size, flags);
}

void *ldv_kmem_cache_zalloc(struct kmem_cache *cachep, gfp_t flags)
{
	return ldv_kzalloc(cachep->size, flags);
}

void ldv_kmem_cache_free(struct kmem_cache *cachep, void *objp)
{
	ldv_free(objp);
}

void ldv_kmem_cache_destroy(struct kmem_cache *cachep)
{
	ldv_free(cachep);
}
