#ifndef __VERIFIER_MEMORY_H
#define __VERIFIER_MEMORY_H

#include <linux/types.h>

extern void *ldv_malloc(size_t size);
extern void *ldv_calloc(size_t nmemb, size_t size);
extern void ldv_free(void *s);
extern void ldv_verifier_free(void *s);
extern void *ldv_verifier_malloc(size_t size);
extern void *ldv_verifier_calloc(size_t nmemb, size_t size);
extern void *ldv_verifier_zalloc(size_t size);
extern void *external_allocated_data(void);

#endif /* __VERIFIER_MEMORY_H */
