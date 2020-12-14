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
#include <ldv/verifier/memory.h>
#include <ldv/verifier/nondet.h>

typedef void *loff_t;
typedef long u32;
typedef int u16;
typedef short u8;

/* SV-COMP functions intended for modelling nondeterminism. */
char __VERIFIER_nondet_char(void);
int __VERIFIER_nondet_int(void);
float __VERIFIER_nondet_float(void);
long __VERIFIER_nondet_long(void);
size_t __VERIFIER_nondet_size_t(void);
loff_t __VERIFIER_nondet_loff_t(void);
u32 __VERIFIER_nondet_u32(void);
u16 __VERIFIER_nondet_u16(void);
u8 __VERIFIER_nondet_u8(void);
unsigned char __VERIFIER_nondet_uchar(void);
unsigned int __VERIFIER_nondet_uint(void);
unsigned short __VERIFIER_nondet_ushort(void);
unsigned __VERIFIER_nondet_unsigned(void);
unsigned long __VERIFIER_nondet_ulong(void);
unsigned long long __VERIFIER_nondet_ulonglong(void);
void *__VERIFIER_nondet_pointer(void);
void __VERIFIER_assume(int expression);

int ldv_undef_int(void)
{
	return __VERIFIER_nondet_int();
}

int ldv_random_int(int begin, int end)
{
	int ret;

	if (begin >= end)
        return begin;
  	else {
        ret = __VERIFIER_nondet_int();
        ldv_assume(ret >= begin);
        ldv_assume(ret < end);
        return ret;
	}
}

int ldv_undef_long(void)
{
	return __VERIFIER_nondet_long();
}

unsigned int ldv_undef_uint(void)
{
	return __VERIFIER_nondet_uint();
}

void *ldv_undef_ptr(void)
{
	return __VERIFIER_nondet_pointer();
}

unsigned long ldv_undef_ulong(void)
{
	return __VERIFIER_nondet_ulong();
}

unsigned long long ldv_undef_ulonglong(void)
{
	return __VERIFIER_nondet_ulonglong();
}

int ldv_undef_int_positive(void)
{
	int ret = ldv_undef_int();

	ldv_assume(ret > 0);

	return ret;
}

int ldv_undef_int_negative(void)
{
	int ret = ldv_undef_int();

	ldv_assume(ret < 0);

	return ret;
}

int ldv_undef_int_nonpositive(void)
{
	int ret = ldv_undef_int();

	ldv_assume(ret <= 0);

	return ret;
}

void *ldv_undef_ptr_non_null(void)
{
	void *ret = ldv_undef_ptr();

	ldv_assume(ret);

	return ret;
}
