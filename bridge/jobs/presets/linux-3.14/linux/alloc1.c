#include <linux/gfp.h>
#include <linux/ldv/common.h>
#include <verifier/common.h>
#include <linux/ldv/irq.h>

/* MODEL_FUNC_DEF Check that correct flag was used in context of interrupt */
void ldv_check_alloc_flags(gfp_t flags) 
{
	/* ASSERT GFP_ATOMIC flag should be used in context of interrupt */
	ldv_assert("linux:alloc:irq:wrong flags", !ldv_in_interrupt_context() || (flags == GFP_ATOMIC));
}

/* MODEL_FUNC_DEF Check that we are not in context of interrupt */
void ldv_check_alloc_nonatomic(void)
{
	if (ldv_in_interrupt_context())
	{
		/* ASSERT We should not be in context of interrupt */
		ldv_assert("linux:alloc:irq:nonatomic", 0);
	}
}