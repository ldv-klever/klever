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
#include <ldv/linux/common.h>
#include <ldv/verifier/common.h>
#include <ldv/verifier/memory.h>

/* NOTE At the beginning nothing is allocated. */
int ldv_alloc_count = 0;

void ldv_after_alloc(void *res)
{
	ldv_assume(res <= LDV_PTR_MAX);
	if (res != 0) {
		/* NOTE One more "memory" is allocated. */
		ldv_alloc_count++;
	}
}

void* ldv_nonzero_alloc(size_t size)
{
	void *res = ldv_malloc(size);
	ldv_after_alloc(res);
	// Functions, like memdup_user returns either valid pointer, or ptr_err.
	ldv_assume(res != 0);
	if (res <= LDV_PTR_MAX) {
		/* NOTE One more "memory" is allocated. */
		ldv_alloc_count++;
	}
	/* NOTE Memory */
	return res;
}

void ldv_memory_free(void)
{
	/* NOTE Free a "memory". */
	ldv_alloc_count--;
}

void ldv_check_final_state(void)
{
	/* ASSERT Nothing should be allocated at the end. */
	ldv_assert(ldv_alloc_count <= 0);
	ldv_assert(ldv_alloc_count >= 0);
}
