#include <linux/types.h>
#include <verifier/memory.h>

extern void ldv_check_alloc_flags(gfp_t flags);
extern void ldv_after_alloc(void *res);

void *ldv_kzalloc(size_t size, gfp_t flags)
{
	void *res;

	ldv_check_alloc_flags(flags);
	res = ldv_verifier_zalloc(size);
	ldv_after_alloc(res);

	return res;
}
