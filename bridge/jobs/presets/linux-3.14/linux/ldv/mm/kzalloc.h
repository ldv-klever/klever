#include <linux/types.h>

extern void *ldv_kzalloc(size_t size, gfp_t flags);

extern void ldv_check_alloc_flags(gfp_t flags);
extern void ldv_after_alloc(void *res);
