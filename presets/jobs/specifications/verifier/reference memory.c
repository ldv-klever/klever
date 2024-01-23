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
#include <ldv/verifier/nondet.h>
#include <ldv/verifier/memory.h>

unsigned int ldv_is_memory_alloc_failures = 1;

void *ldv_reference_malloc(size_t size)
{
	void *res;

	if (ldv_is_memory_alloc_failures && ldv_undef_int())
		return NULL;

	/* Always successful according to SV-COMP definition. */
	res = malloc(size);
	ldv_assume(res != NULL);

	return res;
}

void *ldv_reference_calloc(size_t nmemb, size_t size)
{
	void *res;

	if (ldv_is_memory_alloc_failures && ldv_undef_int())
		return NULL;

	res = calloc(nmemb, size);
	ldv_assume(res != NULL);

	return res;
}

void *ldv_reference_zalloc(size_t size)
{
	void *res;

	if (ldv_is_memory_alloc_failures && ldv_undef_int())
		return NULL;

	res = calloc(1, size);
	ldv_assume(res != NULL);

	return res;
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
		__VERIFIER_memcpy(res, ptr, size);
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

void *ldv_reference_xcalloc(size_t nmemb, size_t size)
{
	void *res;

	res = calloc(nmemb, size);
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
    	/* NOTE2 Allocate special memory any usage of which will be considered as correct by verification tools (https://tinyurl.com/cu4ycvbx). */
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
    	/* NOTE2 Allocate special memory any usage of which will be considered as correct by verification tools (https://tinyurl.com/cu4ycvbx). */
		res = external_allocated_data();
		__VERIFIER_memset(res, 0, sizeof(res));
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

void *ldv_reference_xmalloc_unknown_size(void)
{
	void *res;

    /* NOTE2 Allocate special memory any usage of which will be considered as correct by verification tools (https://tinyurl.com/cu4ycvbx). */
	res = external_allocated_data();
	ldv_assume(res != NULL);

	return res;
}
