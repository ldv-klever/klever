/*
 * Copyright (c) 2020 ISP RAS (http://www.ispras.ru)
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
#include <ldv/common/list.h>
#include <ldv/linux/common.h>
#include <ldv/linux/device.h>
#include <ldv/linux/slab.h>
#include <ldv/verifier/memory.h>

void *ldv_devm_kmalloc(size_t size, gfp_t flags)
{
	void *res;

	ldv_check_alloc_flags(flags);
	res = ldv_malloc(size);
	ldv_save_allocated_memory_to_list(res);

	return res;
}

void *ldv_devm_kzalloc(size_t size, gfp_t flags)
{
	void *res;

	ldv_check_alloc_flags(flags);
	res = ldv_zalloc(size);
	ldv_save_allocated_memory_to_list(res);

	return res;
}

void *ldv_devm_kmalloc_array(size_t n, size_t size, gfp_t flags)
{
	void *res;

	ldv_check_alloc_flags(flags);
	res = ldv_malloc(n * size);
	ldv_save_allocated_memory_to_list(res);

	return res;
}

void *ldv_devm_kcalloc(size_t n, size_t size, gfp_t flags)
{
	void *res;

	ldv_check_alloc_flags(flags);
	res = ldv_calloc(n, size);
	ldv_save_allocated_memory_to_list(res);

	return res;
}
