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
 * ee the License for the specific language governing permissions and
 * limitations under the License.
 */

#ifndef __VERIFIER_COMMON_H
#define __VERIFIER_COMMON_H

/* https://sv-comp.sosy-lab.org/2017/rules.php */
void __VERIFIER_error(void);
void __VERIFIER_assume(int expr);

/* If expression is zero ldv_assert() causes program to reach error function
 * call. */
extern void ldv_assert(const char *, int expr);

/* Internal alias for __VERIFIER_assume(). Proceed only if expression is
 * nonzero. */
#define ldv_assume(expr) __VERIFIER_assume(expr)

#endif /* __VERIFIER_COMMON_H */
