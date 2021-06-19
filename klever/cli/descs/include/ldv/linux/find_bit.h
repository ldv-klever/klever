/*
 * Copyright (c) 2021 ISP RAS (http://www.ispras.ru)
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

#ifndef __LDV_LINUX_FIND_BIT_H
#define __LDV_LINUX_FIND_BIT_H

extern unsigned long ldv_find_first_bit(const unsigned long *addr, unsigned long size);
extern unsigned long ldv_find_next_bit(const unsigned long *addr, unsigned long size, unsigned long offset);
extern unsigned long ldv_find_next_zero_bit(const unsigned long *addr, unsigned long size, unsigned long offset);

extern void ldv_check_find_bit_offset(unsigned long size, unsigned long offset);

#endif /* __LDV_LINUX_FIND_BIT_H */
