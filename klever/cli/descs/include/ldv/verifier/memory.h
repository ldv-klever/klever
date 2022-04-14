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

#ifndef __LDV_VERIFIER_MEMORY_H
#define __LDV_VERIFIER_MEMORY_H

#if defined(LDV_X86_64) || defined(LDV_ARM64)
typedef unsigned long size_t;
#else
typedef unsigned int size_t;
#endif

/* ISO/IEC 9899:1999 specification, § 7.20.3 "Memory management functions". */
extern void *malloc(size_t size);
extern void *calloc(size_t nmemb, size_t size);
extern void free(void *);


/* ISO/IEC 9899:1999 specification, § 7.21.2 "Copying functions". */
extern void *memcpy(void *s1, const void *s2, size_t n);

/* ISO/IEC 9899:1999 specification, § 7.21.6 "Miscellaneous functions". */
extern void *memset(void *s, int c, size_t n);

/* In some cases, e.g. for OS kernels, mem*() functions can be defined in some fancy way, so that verifiers will not
   recognize them anymore. One should bypass this issue by developing appropriate models referring __VERIFIER_mem*()
   analogues. Those functions are known for verifiers through appropriate configuration settings. */
extern void *__VERIFIER_memcpy(void *s1, const void *s2, size_t n);
extern void *__VERIFIER_memset(void *s, int c, size_t n);


extern unsigned int ldv_is_memory_alloc_failures;

// Implementations for direct use in specifications and models
extern void *ldv_malloc(size_t size);
extern void *ldv_calloc(size_t nmemb, size_t size);
extern void *ldv_zalloc(size_t size);
extern void ldv_free(void *s);

extern void *ldv_realloc(void *ptr, size_t size);

extern void *ldv_xmalloc(size_t size);
extern void *ldv_xcalloc(size_t nmemb, size_t size);
extern void *ldv_xzalloc(size_t size);

extern void *ldv_malloc_unknown_size(void);
extern void *ldv_calloc_unknown_size(void);
extern void *ldv_zalloc_unknown_size(void);

// Reference implementations to use at definition of specific implementations
extern void *ldv_reference_malloc(size_t size);
extern void *ldv_reference_calloc(size_t nmemb, size_t size);
extern void *ldv_reference_zalloc(size_t size);
extern void ldv_reference_free(void *s);

extern void *ldv_reference_realloc(void *ptr, size_t size);

extern void *ldv_reference_xmalloc(size_t size);
extern void *ldv_reference_xcalloc(size_t nmemb, size_t size);
extern void *ldv_reference_xzalloc(size_t size);

extern void *ldv_reference_malloc_unknown_size(void);
extern void *ldv_reference_calloc_unknown_size(void);
extern void *ldv_reference_zalloc_unknown_size(void);

/**
 * ldv_xmalloc_unknown_size() - This function is intended just for EMG that likes to pass some size even
 *                              when it wants to allocate memory of unknown size.
 */
extern void *ldv_xmalloc_unknown_size(size_t size);

extern void *ldv_reference_xmalloc_unknown_size(size_t size);

extern void *external_allocated_data(void);

#endif /* __LDV_VERIFIER_MEMORY_H */
