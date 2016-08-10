#include <linux/types.h>
#include <linux/ldv/gfp.h>
#include <verifier/common.h>

extern int ldv_exclusive_spin_is_locked(void);

/* MODEL_FUNC_DEF Check that correct flag was used when spinlock is aquired */
void ldv_check_alloc_flags(gfp_t flags)
{
	if (!CHECK_WAIT_FLAGS(flags)) {
		/* ASSERT __GFP_WAIT flag should be unset (GFP_ATOMIC or GFP_NOWAIT flag should be used) when spinlock{{ arg_sign.text }} is aquired */
		ldv_assert("linux:alloc:spinlock::wrong flags", !ldv_exclusive_spin_is_locked());
	}
}

/* MODEL_FUNC_DEF Check that spinlock is not acquired */
void ldv_check_alloc_nonatomic(void)
{
	/* ASSERT Spinlock{{ arg_sign.text }} should not be acquired */
	ldv_assert("linux:alloc:spinlock::nonatomic", !ldv_exclusive_spin_is_locked());
}
