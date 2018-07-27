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
 * ee the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <linux/types.h>

/* MODEL_FUNC Add integer to atomic variable */
void ldv_atomic_add(int i, atomic_t *v)
{
	v->counter += i;
}

/* MODEL_FUNC Subtract integer from atomic variable */
void ldv_atomic_sub(int i, atomic_t *v)
{
	v->counter -= i;
}

/* MODEL_FUNC Subtract value from atomic variable and test result */
int ldv_atomic_sub_and_test(int i, atomic_t *v)
{
	v->counter -= i;
	if (v->counter) {
		return 0;
	}
	return 1;
}

/* MODEL_FUNC Increment atomic variable */
void ldv_atomic_inc(atomic_t *v)
{
	v->counter++;
}

/* MODEL_FUNC Decrement atomic variable */
void ldv_atomic_dec(atomic_t *v)
{
	v->counter--;
}

/* MODEL_FUNC Decrement atomic variable and test result */
int ldv_atomic_dec_and_test(atomic_t *v)
{
	v->counter--;
	if (v->counter) {
		return 0;
	}
	return 1;
}

/* MODEL_FUNC Increment atomic variable and test result */
int ldv_atomic_inc_and_test(atomic_t *v)
{
	v->counter++;
	if (v->counter) {
		return 0;
	}
	return 1;
}

/* MODEL_FUNC Add integer to atomic variable and return result */
int ldv_atomic_add_return(int i, atomic_t *v)
{
	v->counter+=i;
	return v->counter;
}

/* MODEL_FUNC Add integer to atomic variable and test result if negative */
int ldv_atomic_add_negative(int i, atomic_t *v)
{
	v->counter+=i;
	return v->counter < 0;
}

/* MODEL_FUNC Increment short integer and return result */
int ldv_atomic_inc_short(short int *v)
{
	*v = *v + 1;
	return *v;
}
