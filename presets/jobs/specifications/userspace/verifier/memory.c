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

#include <stddef.h>
#include <../verifier/reference memory.c>

void *ldv_malloc(size_t size)
{
    return ldv_reference_malloc(size);
}

void *ldv_calloc(size_t nmemb, size_t size)
{
    return ldv_reference_calloc(nmemb, size);
}

void *ldv_zalloc(size_t size)
{
	return ldv_reference_zalloc(size);
}

void ldv_free(void *s)
{
	ldv_reference_free(s);
}

void *ldv_xmalloc(size_t size)
{
    return ldv_reference_xmalloc(size);
}

void *ldv_xzalloc(size_t size)
{
	return ldv_reference_xzalloc(size);
}

void *ldv_malloc_unknown_size(void)
{
    return ldv_reference_malloc_unknown_size();
}

void *ldv_calloc_unknown_size(void)
{
	return ldv_reference_calloc_unknown_size();
}

void *ldv_zalloc_unknown_size(void)
{
	return ldv_reference_zalloc_unknown_size();
}

void *ldv_xmalloc_unknown_size(void)
{
    return ldv_reference_xmalloc_unknown_size();
}

void *ldv_xmalloc_unknown_size_t(size_t size)
{
    return ldv_xmalloc_unknown_size();
}

void *ldv_realloc(void *ptr, size_t size)
{
    return ldv_reference_realloc(ptr, size);
}