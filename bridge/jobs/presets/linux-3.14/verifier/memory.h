#ifndef __VERIFIER_MEMORY_H
#define __VERIFIER_MEMORY_H

#include <linux/types.h>

/* Pointers greater then this number correspond to errors. We can't use
 * original value defined in linux/err.h (~(unsigned long)-4095) since it is
 * too hard for verifiers.
 */
#define LDV_PTR_MAX ((unsigned int)-1)

extern void *ldv_malloc(size_t size);
extern void *ldv_calloc(size_t nmemb, size_t size);
extern void *ldv_zalloc(size_t size);
extern void ldv_free(void *s);
void *ldv_xmalloc(size_t size);

extern void *external_allocated_data(void);
extern void *ldv_malloc_unknown_size(void);
extern void *ldv_calloc_unknown_size(void);
extern void *ldv_zalloc_unknown_size(void);

/**
 * ldv_xmalloc_unknown_size() - This function is intended just for EMG that likes to pass some size even
 *                             when it wants to allocate memory of unknown size.
 */
extern void *ldv_xmalloc_unknown_size(size_t size);

#endif /* __VERIFIER_MEMORY_H */
