/*
 * Copyright (c) 2022 ISP RAS (http://www.ispras.ru)
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

#include <linux/kernel.h>
#include <linux/limits.h>
#include <linux/types.h>
#include <ldv/linux/overflow.h>
#include <ldv/verifier/common.h>


/*
 * These models are very rough, but they can work pretty well at verification of Linux drivers.
 * First of all they assume that nobody invokes the appropriate (macro) functions with any of their arguments equal to
 * SIZE_MAX. Nevertheless, this can be the case when one provides nondeterministic values to them at verification.
 * Models consider such the case as an overflow. Moreover, they result in reporting corresponding unsafes to catch all
 * these cases as early as possible. Otherwise, verification tools can report safes or unknowns (timeouts) hiding lack
 * of deterministic data. BTW, this trick does not work always since verification tools can decide that nondeterministic
 * values are not SIZE_MAX and still find some issues later.
 * As for the essence of the corresponding (macro) functions, these models do not accurately check for overflows since
 * it is pretty hard to do. At least they compute some result rather than the original code that invokes builtin
 * functions which the verification tool does not know. Probably verification tools will detect some issues in case of
 * overflows themselves later.
 */

static void ldv_check_undef_args(size_t a, size_t b)
{
	if (a == SIZE_MAX)
		/* ASSERT First argument is likely nondeterministic (you may need to add/fix models) */
		ldv_assert();

	if (b == SIZE_MAX)
		/* ASSERT Second argument is likely nondeterministic (you may need to add/fix models) */
		ldv_assert();
}

int ldv_check_add_overflow(size_t a, size_t b, size_t *d)
{
	unsigned long long res;

	ldv_check_undef_args(a, b);
	*d = a + b;

	return 0;
}

int ldv_check_sub_overflow(size_t a, size_t b, size_t *d)
{
	unsigned long long res;

	ldv_check_undef_args(a, b);
	*d = a - b;

	return 0;
}

int ldv_check_mul_overflow(size_t a, size_t b, size_t *d)
{
	unsigned long long res;

	ldv_check_undef_args(a, b);
	*d = a * b;

	return 0;
}
