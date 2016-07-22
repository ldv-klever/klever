#include <linux/types.h>
#include <verifier/memory.h>

extern void ldv_check_alloc_flags(gfp_t flags);
extern void ldv_after_alloc(void *res);

void *ldv_kzalloc(gfp_t flags)
{
	ldv_check_alloc_flags(flags);
	void *res = ldv_verifier_zalloc(1);
	ldv_after_alloc(res);
	return res;
}