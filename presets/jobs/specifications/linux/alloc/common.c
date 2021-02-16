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
#include <ldv/linux/err.h>
#include <ldv/verifier/common.h>
#include <ldv/verifier/memory.h>
#include <ldv/verifier/nondet.h>

void *ldv_common_alloc(gfp_t flags)
{
	ldv_check_alloc_flags(flags);
	return ldv_malloc_unknown_size();
}

int ldv_common_alloc_return_int(gfp_t flags)
{
	ldv_check_alloc_flags(flags);
	return ldv_undef_int();
}

void *ldv_common_alloc_without_flags(void)
{
	ldv_check_alloc_nonatomic();
	return ldv_malloc_unknown_size();
}

void *ldv_common_zalloc(gfp_t flags)
{
	ldv_check_alloc_flags(flags);
	return ldv_zalloc_unknown_size();
}
