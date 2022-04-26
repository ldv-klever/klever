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

#include <linux/types.h>

void ldv_atomic_set(atomic_t *v, int i)
{
	v->counter = i;
}

int ldv_atomic_read(const atomic_t *v)
{
	return v->counter;
}

void ldv_atomic_add(int i, atomic_t *v)
{
	v->counter += i;
}

void ldv_atomic_sub(int i, atomic_t *v)
{
	v->counter -= i;
}

int ldv_atomic_sub_and_test(int i, atomic_t *v)
{
	v->counter -= i;

	if (v->counter)
		return 0;

	return 1;
}

void ldv_atomic_inc(atomic_t *v)
{
	v->counter++;
}

void ldv_atomic_dec(atomic_t *v)
{
	v->counter--;
}

int ldv_atomic_dec_and_test(atomic_t *v)
{
	v->counter--;

	if (v->counter)
		return 0;

	return 1;
}

int ldv_atomic_inc_and_test(atomic_t *v)
{
	v->counter++;

	if (v->counter)
		return 0;

	return 1;
}

int ldv_atomic_add_return(int i, atomic_t *v)
{
	v->counter += i;
	return v->counter;
}

int ldv_atomic_add_negative(int i, atomic_t *v)
{
	v->counter += i;
	return v->counter < 0;
}

int ldv_atomic_inc_short(short int *v)
{
	*v = *v + 1;
	return *v;
}
