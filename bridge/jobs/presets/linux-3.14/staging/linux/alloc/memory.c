/*
 * Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
 * Institute for System Programming of the Russian Academy of Sciences
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
 * ee the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <linux/types.h>
#include <linux/ldv/common.h>
#include <verifier/common.h>
#include <verifier/memory.h>

/* NOTE At the beginning nothing is allocated. */
int ldv_alloc_count = 0;

/* MODEL_FUNC Allocate a "memory". */
void ldv_after_alloc(void *res)
{
	ldv_assume(res <= LDV_PTR_MAX);
	if (res != 0) {
		/* NOTE One more "memory" is allocated. */
		ldv_alloc_count++;
	}
}

/* MODEL_FUNC Allocate a non zero "memory", but can return PTR_ERR. */
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

/* MODEL_FUNC Free a "memory". */
void ldv_memory_free(void)
{
	/* NOTE Free a "memory". */
	ldv_alloc_count--;
}

/* MODEL_FUNC All allocated memory should be freed at the end. */
void ldv_check_final_state(void)
{
	/* ASSERT Nothing should be allocated at the end. */
	ldv_assert("linux:alloc::more at exit", ldv_alloc_count <= 0);
	ldv_assert("linux:alloc::less at exit", ldv_alloc_count >= 0);
}
