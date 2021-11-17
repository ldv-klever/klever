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

#ifndef __LDV_LINUX_BITMAP_H
#define __LDV_LINUX_BITMAP_H

extern void ldv_set_bit(long nr, volatile unsigned long *addr);
extern void ldv_clear_bit(long nr, volatile unsigned long *addr);

extern void ldv_bitmap_set(unsigned long *map, unsigned int start, int nbits);
extern void ldv_bitmap_clear(unsigned long *map, unsigned int start, int nbits);

extern void ldv_bitmap_zero(unsigned long *dst, unsigned int nbits);

extern unsigned long ldv_bitmap_find_next_zero_area(unsigned long *map, unsigned long size, unsigned long start, unsigned int nr, unsigned long align_mask);

#endif /* __LDV_LINUX_BITMAP_H */
