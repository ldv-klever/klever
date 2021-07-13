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

#ifndef __LDV_VERIFIER_COMMON_H
#define __LDV_VERIFIER_COMMON_H

/* https://sv-comp.sosy-lab.org/2017/rules.php */
void __VERIFIER_error(void);
void __VERIFIER_assume(int expr);

#ifdef LDV_MEMORY_SAFETY
/* Deliberate NULL pointer dereference corresponding to violations of requirement specifications expressed and checked
   using memory safety properties or false alarms. */
#define ldv_assert() ({*(char *)0;})
#else
/* Unconditionally reach call of error function, i.e. __VERIFIER_error(). Verification tools treats this call of the
   special function as a solution of the reachability task that can correspond to either a fault or a false alarm. */
#define ldv_assert() __VERIFIER_error()
#endif

/* Proceed further only if expression is nonzero. */
#define ldv_assume(expr) __VERIFIER_assume(expr)

#endif /* __LDV_VERIFIER_COMMON_H */
