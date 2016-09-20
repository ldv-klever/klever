/*
 * Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
 * Institute for System Programming of the Russian Academy of Sciences
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
#include <linux/ldv/err.h>
#include <verifier/common.h>
#include <verifier/nondet.h>
#include <verifier/memory.h>

/* ISO/IEC 9899:1999 specification. p. 313, § 7.20.3 "Memory management functions". */
extern void *malloc(size_t size);
extern void *calloc(size_t nmemb, size_t size);
extern void free(void *);
extern void *memset(void *s, int c, size_t n);

void *ldv_malloc(size_t size)
{
	if (ldv_undef_int()) {
		void *res = malloc(size);
		ldv_assume(res != NULL);
		ldv_assume(!ldv_is_err(res));
		return res;
	}
	else {
		return NULL;
	}
}

void *ldv_calloc(size_t nmemb, size_t size)
{
	if (ldv_undef_int()) {
		void *res = calloc(nmemb, size);
		ldv_assume(res != NULL);
		ldv_assume(!ldv_is_err(res));
		return res;
	}
	else {
		return NULL;
	}
}

void *ldv_zalloc(size_t size)
{
	return ldv_calloc(1, size);
}

void ldv_free(void *s)
{
	free(s);
}

void *ldv_xmalloc(size_t size)
{
    void *res = malloc(size);
    ldv_assume(res != NULL);
    ldv_assume(!ldv_is_err(res));
    return res;
}

void *ldv_xzalloc(size_t size)
{
	void *res = calloc(1, size);
	ldv_assume(res != NULL);
	ldv_assume(!ldv_is_err(res));
	return res;
}

void *ldv_malloc_unknown_size(void)
{
	if (ldv_undef_int()) {
		void *res = external_allocated_data();
		ldv_assume(res != NULL);
		ldv_assume(!ldv_is_err(res));
		return res;
	}
	else {
		return NULL;
	}
}

void *ldv_calloc_unknown_size(void)
{
	if (ldv_undef_int()) {
		void *res = external_allocated_data();
		memset(res, 0, sizeof(res));
		ldv_assume(res != NULL);
		ldv_assume(!ldv_is_err(res));
		return res;
	}
	else {
		return NULL;
	}
}

void *ldv_zalloc_unknown_size(void)
{
	return ldv_calloc_unknown_size();
}

void *ldv_xmalloc_unknown_size(size_t size)
{
	void *res = external_allocated_data();
	ldv_assume(res != NULL);
	ldv_assume(!ldv_is_err(res));
	return res;
}
