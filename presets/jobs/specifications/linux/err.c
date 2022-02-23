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

#include <linux/err.h>
#include <ldv/linux/err.h>
#include <ldv/verifier/common.h>

/* Pointers greater then this number correspond to errors. */
#define LDV_PTR_MAX ((unsigned long)-MAX_ERRNO)

bool ldv_is_err(const void *ptr)
{
	/* This long form is necessary for CPAchecker SMG. Please, do not change it to, say,
	   "return (unsigned long)ptr >= LDV_PTR_MAX". */
	if ((unsigned long)ptr >= LDV_PTR_MAX)
		return 1;
	else
		return 0;
}

void *ldv_err_ptr(long error)
{
	unsigned long result;

	ldv_assume(error < 0);
	ldv_assume(error >= -MAX_ERRNO);
	result = (LDV_PTR_MAX - 1) - error;
	ldv_assume(result >= LDV_PTR_MAX);

	return (void *)result;
}

long ldv_ptr_err(const void *ptr)
{
	long result;

	ldv_assume((unsigned long) ptr >= LDV_PTR_MAX);
	result = (LDV_PTR_MAX - 1) - (unsigned long)ptr;
	ldv_assume(result < 0);
	ldv_assume(result >= -MAX_ERRNO);

	return result;
}

bool ldv_is_err_or_null(const void *ptr)
{
	return !ptr || ldv_is_err(ptr);
}
