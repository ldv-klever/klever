#ifndef __VERIFIER_MEMORY_H
#define __VERIFIER_MEMORY_H

#include <linux/types.h>

extern void *ldv_malloc(size_t size);
extern void *ldv_calloc(size_t nmemb, size_t size);
extern void *ldv_zalloc(size_t size);
extern void ldv_free(void *s);

extern void *external_allocated_data(void);

extern void *ldv_malloc_unknown_size(void);
extern void *ldv_calloc_unknown_size(void);
extern void *ldv_zalloc_unknown_size(void);

/* This function is intended just for EMG that likes to pass some size even
 * when it wants to allocate memory of unknown size.
 */
extern void *__ldv_malloc_unknown_size(size_t size);

#endif /* __VERIFIER_MEMORY_H */
