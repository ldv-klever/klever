#ifndef __VERIFIER_MEMORY_H
#define __VERIFIER_MEMORY_H
#include <linux/kernel.h>

/*ISO/IEC 9899:1999 specification. p. 313, paragraph 7.20.3 "Memory management functions"*/
extern void *ldv_malloc(size_t size);
extern void *ldv_calloc(size_t nmemb, size_t size);
extern void ldv_free(void *s);

#endif /* __VERIFIER_MEMORY_H */
