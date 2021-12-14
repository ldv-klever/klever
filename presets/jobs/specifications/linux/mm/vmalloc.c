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

#include <linux/types.h>
#include <ldv/linux/common.h>
#include <ldv/linux/vmalloc.h>
#include <ldv/verifier/memory.h>

void *ldv_vmalloc(unsigned long size)
{
	void *res;

	ldv_check_alloc_nonatomic();
	res = ldv_malloc(size);

	return res;
}

void *ldv_vzalloc(unsigned long size)
{
	void *res;

	ldv_check_alloc_nonatomic();
	res = ldv_zalloc(size);

	return res;
}

void ldv_vfree(const void *addr)
{
    ldv_free((void *)addr);
}
