#include <linux/types.h>
#include <linux/ldv/gfp.h>
#include <verifier/common.h>

/* MODEL_FUNC_DEF Check that correct flag was used when spinlock is aquired */
void ldv_check_alloc_flags(gfp_t flags)
{
	if (CHECK_WAIT_FLAGS(flags)) {
		// for arg_sign in spinlock_arg_signs
		/* ASSERT __GFP_WAIT flag should be unset (GFP_ATOMIC or GFP_NOWAIT flag should be used) when spinlock{{ arg_sign.text }} is aquired */
		ldv_assert("linux:alloc:spin lock:wrong flags", !ldv_exclusive_spin_is_locked{{ arg_sign.id }}());
		// endfor
	}
}

/* MODEL_FUNC_DEF Check that spinlock is not acquired */
void ldv_check_alloc_nonatomic(void)
{
	/* ASSERT Spinlock{{ arg_sign.text }} should not be acquired */
	ldv_assert("linux:alloc:spin lock:nonatomic", !ldv_exclusive_spin_is_locked());
}