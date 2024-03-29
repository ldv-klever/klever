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

#ifndef __LDV_LINUX_OVERFLOW_H
#define __LDV_LINUX_OVERFLOW_H

#include <linux/types.h>

/* Old versions of the Linux kernel do not define this constant. */
#ifndef SIZE_MAX
#define SIZE_MAX	(~(size_t)0)
#endif

extern int ldv_check_add_overflow(size_t a, size_t b, size_t *d);
extern int ldv_check_sub_overflow(size_t a, size_t b, size_t *d);
extern int ldv_check_mul_overflow(size_t a, size_t b, size_t *d);

#endif /* __LDV_LINUX_OVERFLOW_H */
