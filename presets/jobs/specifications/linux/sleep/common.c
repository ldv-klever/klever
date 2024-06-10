/*
 * Copyright (c) 2024 ISP RAS (http://www.ispras.ru)
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

#include <ldv/linux/common.h>
#include <ldv/linux/err.h>
#include <ldv/verifier/common.h>
#include <ldv/verifier/nondet.h>

extern int ldv_exclusive_spin_is_locked(void);
extern int ldv_is_rw_locked(void);

void ldv_common_sleep(void)
{
    if (ldv_exclusive_spin_is_locked()) {
        /* ASSERT shouldnt sleep in spinlock*/
        ldv_assert();
    }
    if (ldv_in_interrupt_context()) {
        /* ASSERT shouldnt sleep in interrupt context*/
        ldv_assert();
    }
    if (ldv_is_rw_locked()) {
        /* ASSERT shouldnt sleep in rwlock*/
        ldv_assert();
    }
}
