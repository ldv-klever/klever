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

#include <linux/ldv/err.h>
#include <verifier/common.h>

long ldv_is_err(const void *ptr)
{
	return ((unsigned long)ptr > LDV_PTR_MAX);
}

void *ldv_err_ptr(long error)
{
	ldv_assume(error < 0);
	return (void *)(LDV_PTR_MAX - error);
}

long ldv_ptr_err(const void *ptr)
{
	ldv_assume((unsigned long) ptr > LDV_PTR_MAX);
	return (long)(LDV_PTR_MAX - (unsigned long)ptr);
}

long ldv_is_err_or_null(const void *ptr)
{
	return !ptr || ldv_is_err((unsigned long)ptr);
}
