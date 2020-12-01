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

#include <ldv/linux/err.h>
#include <ldv/verifier/common.h>

long ldv_is_err(const void *ptr)
{
	if ((unsigned long)ptr > LDV_PTR_MAX)
		return 1;
	else
		return 0;
}

void *ldv_err_ptr(long error)
{
	ldv_assume(error < 0);
	ldv_assume(error > -LDV_MAX_ERRNO);
	unsigned long result = LDV_PTR_MAX - error;
	ldv_assume(result > LDV_PTR_MAX);

	return (void *)result;
}

long ldv_ptr_err(const void *ptr)
{
	ldv_assume((unsigned long) ptr > LDV_PTR_MAX);
	long result = LDV_PTR_MAX - (unsigned long)ptr;
	ldv_assume(result < 0);
	ldv_assume(result > -LDV_MAX_ERRNO);

	return result;
}

long ldv_is_err_or_null(const void *ptr)
{
	return !ptr || ldv_is_err((unsigned long)ptr);
}
