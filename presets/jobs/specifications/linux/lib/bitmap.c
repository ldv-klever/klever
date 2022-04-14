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

#include <ldv/linux/bitmap.h>
#include <ldv/linux/find_bit.h>
#include <ldv/verifier/memory.h>

void ldv_bitmap_set(unsigned long *map, unsigned int start, int nbits)
{
	unsigned long *p = map + start / (8 * sizeof(long));
	const unsigned int size = start + nbits;
	int bits_to_set = 8 * sizeof(long) - (start % (8 * sizeof(long)));
	unsigned long mask_to_set = ~0UL << (start & (8 * sizeof(long) - 1));

	while (nbits - bits_to_set >= 0) {
		*p |= mask_to_set;
		nbits -= bits_to_set;
		bits_to_set = 8 * sizeof(long);
		mask_to_set = ~0UL;
		p++;
	}
	if (nbits) {
		mask_to_set &= ~0UL >> (-size & (8 * sizeof(long) - 1));
		*p |= mask_to_set;
	}
}

void ldv_bitmap_clear(unsigned long *map, unsigned int start, int nbits)
{
	unsigned long *p = map + start / (8 * sizeof(long));
	const unsigned int size = start + nbits;
	int bits_to_clear = 8 * sizeof(long) - (start % (8 * sizeof(long)));
	unsigned long mask_to_clear = ~0UL << (start & (8 * sizeof(long) - 1));

	while (nbits - bits_to_clear >= 0) {
		*p &= ~mask_to_clear;
		nbits -= bits_to_clear;
		bits_to_clear = 8 * sizeof(long);
		mask_to_clear = ~0UL;
		p++;
	}
	if (nbits) {
		mask_to_clear &= ~0UL >> (-size & (8 * sizeof(long) - 1));
		*p &= ~mask_to_clear;
	}
}

void ldv_bitmap_zero(unsigned long *dst, unsigned int nbits)
{
	unsigned int len = (nbits + 8 * sizeof(long) - 1) / (8 * sizeof(long)) * sizeof(unsigned long);
	__VERIFIER_memset(dst, 0, len);
}

unsigned long ldv_bitmap_find_next_zero_area(unsigned long *map, unsigned long size, unsigned long start, unsigned int nr, unsigned long align_mask)
{
	unsigned long index, end, i;

again:
	index = ldv_find_next_zero_bit(map, size, start);
	index = (index + align_mask) & ~align_mask;
	end = index + nr;

	if (end > size)
		return end;

	i = ldv_find_next_bit(map, end, index);

	if (i < end) {
		start = i + 1;
		goto again;
	}

	return index;
}
