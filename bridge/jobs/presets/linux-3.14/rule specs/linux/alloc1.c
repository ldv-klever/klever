#include <linux/kernel.h>
#include <linux/gfp.h>
#include <verifier/rcv.h>

extern struct page *ldv_some_page(void);

extern int LDV_IN_INTERRUPT;

/* MODEL_FUNC_DEF Checks if incorrect flag was used in context of interrupt */
void ldv_check_alloc_flags(gfp_t flags) 
{
	/* ASSERT Check value of flags in context of interrupt */
	ldv_assert((LDV_IN_INTERRUPT == 1) || (flags==GFP_ATOMIC));
}

/* MODEL_FUNC_DEF Checks if incorrect flag was used in context of interrupt */
void ldv_check_alloc_nonatomic(void)
{
	if (LDV_IN_INTERRUPT == 2)
		/* ASSERT Check value of flags in context of interrupt */
		ldv_assert(0);
}

/* MODEL_FUNC_DEF Checks if incorrect flag was used in context of interrupt and return some page */
struct page *ldv_check_alloc_flags_and_return_some_page(gfp_t flags)
{
	/* ASSERT Check value of flags in context of interrupt */
	ldv_assert((LDV_IN_INTERRUPT == 1) || (flags == GFP_ATOMIC));
	/* RETURN Return a page pointer (maybe NULL) */
	return ldv_some_page();
}
