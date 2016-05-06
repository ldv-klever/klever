#include <linux/gfp.h>
#include <verifier/common.h>

extern struct page *ldv_some_page(void);

extern int LDV_IN_INTERRUPT;

/* MODEL_FUNC_DEF Check that correct flag was used in context of interrupt */
void ldv_check_alloc_flags(gfp_t flags) 
{
	/* ASSERT GFP_ATOMIC flag should be used in context of interrupt */
	ldv_assert((LDV_IN_INTERRUPT == 1) || (flags == GFP_ATOMIC));
}

/* MODEL_FUNC_DEF Check that we are not in context of interrupt */
void ldv_check_alloc_nonatomic(void)
{
	if (LDV_IN_INTERRUPT == 2)
	{
		/* ASSERT We should not be in context of interrupt */
		ldv_assert(0);
	}
}

/* MODEL_FUNC_DEF Check that correct flag was used in context of interrupt and return some page */
struct page *ldv_check_alloc_flags_and_return_some_page(gfp_t flags)
{
	/* ASSERT GFP_ATOMIC flag should be used in context of interrupt */
	ldv_assert((LDV_IN_INTERRUPT == 1) || (flags == GFP_ATOMIC));
	/* RETURN Some page (maybe NULL) */
	return ldv_some_page();
}
