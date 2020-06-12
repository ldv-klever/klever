/*
 * Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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

#ifndef __LDV_TEST_H
#define __LDV_TEST_H

#include <ldv/verifier/common.h>
#include <ldv/verifier/gcc.h>
#include <ldv/verifier/map.h>
#include <ldv/verifier/memory.h>
#include <ldv/verifier/nondet.h>
#include <ldv/verifier/thread.h>

extern void ldv_expected_error(void);
extern void ldv_unexpected_error(void);
extern void ldv_expected_memory_safety_error(void);
extern void ldv_unexpected_memory_safety_error(void);

#endif /* __LDV_TEST_H */
