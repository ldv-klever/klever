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

/* https://sv-comp.sosy-lab.org/2017/rules.php */
void __VERIFIER_error(void);
void __VERIFIER_assume(int expr);

void ldv_assert(void)
{
	/* NOTE2 Verification tools treats this call of the special function as a solution of the reachability task that can correspond to either a fault or a false alarm */
	__VERIFIER_error();
}

// See corresponding comment in klever/cli/descs/include/ldv/verifier/common.h
//void ldv_assume(int expr)
//{
//    /* NOTE2 Verification tools do not traverse paths where an actual argument of this function is evaluated to zero */
//    __VERIFIER_assume(expr);
//}
