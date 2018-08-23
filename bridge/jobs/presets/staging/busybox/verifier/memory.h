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

#ifndef __VERIFIER_MEMORY_H
#define __VERIFIER_MEMORY_H

#include <linux/types.h>

extern void *ldv_malloc(size_t size);
extern void *ldv_calloc(size_t nmemb, size_t size);
extern void *ldv_zalloc(size_t size);
extern void ldv_free(void *s);

void *ldv_xmalloc(size_t size);
void *ldv_xzalloc(size_t size);

extern void *external_allocated_data(void);

extern void *ldv_malloc_unknown_size(void);
extern void *ldv_calloc_unknown_size(void);
extern void *ldv_zalloc_unknown_size(void);

/**
 * ldv_xmalloc_unknown_size() - This function is intended just for EMG that likes to pass some size even
 *                              when it wants to allocate memory of unknown size.
 */
extern void *ldv_xmalloc_unknown_size(size_t size);

#endif /* __VERIFIER_MEMORY_H */
