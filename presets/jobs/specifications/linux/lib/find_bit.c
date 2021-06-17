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

static unsigned long ldv_ffs(unsigned long word)
{
	int num = 0;

	if ((word & 0xffffffff) == 0) {
		num += 32;
		word >>= 32;
	}
	if ((word & 0xffff) == 0) {
		num += 16;
		word >>= 16;
	}
	if ((word & 0xff) == 0) {
		num += 8;
		word >>= 8;
	}
	if ((word & 0xf) == 0) {
		num += 4;
		word >>= 4;
	}
	if ((word & 0x3) == 0) {
		num += 2;
		word >>= 2;
	}
	if ((word & 0x1) == 0)
		num += 1;

	return num;
}

static unsigned long ldv_min(unsigned long a, unsigned long b)
{
	if (a < b)
		return a;

	return b;
}

unsigned long ldv_find_first_bit(const unsigned long *addr, unsigned long size)
{
	unsigned long i;

	for (i = 0; i * 8 * sizeof(long) < size; i++)
		if (addr[i])
			return ldv_min(i * 8 * sizeof(long) + ldv_ffs(addr[i]), size);

	return size;
}

unsigned long ldv_find_next_bit(const unsigned long *addr, unsigned long size, unsigned long offset)
{
	unsigned long tmp;

	tmp = addr[offset / (8 * sizeof(long))];
	tmp &= ~0ULL << (offset & (8 * sizeof(long) - 1));
	offset = offset & ~((__typeof__(offset))(8 * sizeof(long) - 1));

	while (!tmp) {
		offset += 8 * sizeof(long);
		if (offset >= size)
			return size;

		tmp = addr[offset / (8 * sizeof(long))];
	}

	return ldv_min(offset + ldv_ffs(tmp), size);
}

unsigned long ldv_find_next_zero_bit(const unsigned long *addr, unsigned long size, unsigned long offset)
{
	unsigned long tmp;

	tmp = addr[offset / (8 * sizeof(long))];
	tmp ^= ~0UL;
	tmp &= ~0ULL << (offset & (8 * sizeof(long) - 1));
	offset = offset & ~((__typeof__(offset))(8 * sizeof(long) - 1));

	while (!tmp) {
		offset += 8 * sizeof(long);
		if (offset >= size)
			return size;

		tmp = addr[offset / (8 * sizeof(long))];
		tmp ^= ~0UL;
	}

	return ldv_min(offset + ldv_ffs(tmp), size);
}
