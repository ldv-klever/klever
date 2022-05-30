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
 * This model is very rough, but it can work pretty well at verification of Linux drivers.
 * First of all it assumes that nobody invokes __ab_c_size() with any of its arguments equal to SIZE_MAX. Nevertheless,
 * this can be the case when one provides nondeterministic values to this function at verification. The model considers
 * such the case as an overflow. Moreover, it results in reporting corresponding unsafes to catch all these cases as
 * early as possible. Otherwise, verification tools can report safes or unknowns (timeouts) hiding lack of deterministic
 * data. BTW, this trick does not work always since verification tools can decide that nondeterministic values are not
 * SIZE_MAX and find some issues later.
 * As for the essence of the given function, this model does not accurately check for overflows since it is pretty hard
 * to do. At least it computes some result rather than the original function that invokes an unknown builtin function.
 * Probably verification tools will detect some issues in case of overflows later.
 */
size_t ldv_ab_c_size(size_t a, size_t b, size_t c)
{
	unsigned long long res;

	if (a == SIZE_MAX)
		/* ASSERT First argument of __ab_c_size() is nondeterministic (you may need to add/fix models) */
		ldv_assert();

	if (b == SIZE_MAX)
		/* ASSERT Second argument of __ab_c_size() is nondeterministic (you may need to add/fix models) */
		ldv_assert();

	if (c == SIZE_MAX)
		/* ASSERT Third argument of __ab_c_size() is nondeterministic (you may need to add/fix models) */
		ldv_assert();

	return a * b + c;
}
