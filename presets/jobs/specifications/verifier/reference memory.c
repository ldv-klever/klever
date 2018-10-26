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

#include <verifier/common.h>
#include <verifier/nondet.h>
#include <verifier/memory.h>

/* ISO/IEC 9899:1999 specification, § 7.20.3 "Memory management functions". */
extern void *malloc(size_t size);
extern void *calloc(size_t nmemb, size_t size);
extern void free(void *);

/* ISO/IEC 9899:1999 specification, § 7.21.2 "Copying functions". */
extern void *memcpy(void *s1, const void *s2, size_t n);

/* ISO/IEC 9899:1999 specification, § 7.21.6 "Miscellaneous functions". */
extern void *memset(void *s, int c, size_t n);

void *ldv_reference_malloc(size_t size)
{
	void *res;

	if (ldv_undef_int()) {
		/* Always successful according to SV-COMP definition. */
		res = malloc(size);
		ldv_assume(res != NULL);
		return res;
	}
	else
		return NULL;
}

void *ldv_reference_calloc(size_t nmemb, size_t size)
{
	return calloc(nmemb, size);
}

void *ldv_reference_zalloc(size_t size)
{
	return calloc(1, size);
}

void ldv_reference_free(void *s)
{
	free(s);
}

void *ldv_reference_realloc(void *ptr, size_t size)
{
	void *res;

	if (ptr && !size) {
		free(ptr);
		return NULL;
	}

	if (!ptr) {
		res = malloc(size);
		return res;
	}

	if (ldv_undef_int()) {
		/* Always successful according to SV-COMP definition. */
		res = malloc(size);
		ldv_assume(res != NULL);
		/* TODO: Maybe a better solution exists. */
		memcpy(res, ptr, size);
		free(ptr);

		return res;
	}
	else
		return NULL;
}

void *ldv_reference_xmalloc(size_t size)
{
	void *res;

	res = malloc(size);
	ldv_assume(res != NULL);

	return res;
}

void *ldv_reference_xzalloc(size_t size)
{
	void *res;

	res = calloc(1, size);
	ldv_assume(res != NULL);

	return res;
}

void *ldv_reference_malloc_unknown_size(void)
{
	void *res;

	if (ldv_undef_int()) {
		res = external_allocated_data();
		ldv_assume(res != NULL);
		return res;
	}
	else
		return NULL;
}

void *ldv_reference_calloc_unknown_size(void)
{
	void *res;

	if (ldv_undef_int()) {
		res = external_allocated_data();
		memset(res, 0, sizeof(res));
		ldv_assume(res != NULL);
		return res;
	}
	else
		return NULL;
}

void *ldv_reference_zalloc_unknown_size(void)
{
	return ldv_reference_calloc_unknown_size();
}

void *ldv_reference_xmalloc_unknown_size(size_t size)
{
	void *res;

	res = external_allocated_data();
	ldv_assume(res != NULL);

	return res;
}

