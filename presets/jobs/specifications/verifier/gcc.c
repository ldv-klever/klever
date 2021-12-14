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

#include <ldv/verifier/common.h>

/* Explicit model for GCC function __builtin_expect(). Without this model
 * return value of __builtin_expect() will be treated as nondetermined by
 * verifiers.
 */
long __builtin_expect(long exp, long c)
{
	return exp;
}

/* This function causes the program to exit abnormally. GCC implements this
 * function by using a target-dependent mechanism (such as intentionally
 * executing an illegal instruction) or by calling abort. The mechanism used
 * may vary from release to release so you should not rely on any particular
 * implementation (http://gcc.gnu.org/onlinedocs/gcc/Other-Builtins.html).
 */
void __builtin_trap(void)
{
	ldv_assert();
}
