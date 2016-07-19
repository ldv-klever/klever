#include <linux/types.h>
#include <linux/ldv/gfp.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

/* CHANGE_STATE Spinlock is not acquired at the beginning */
int ldv_spin = 0;

/* MODEL_FUNC_DEF Check that correct flag was used when spinlock is aquired */
void ldv_check_alloc_flags(gfp_t flags)
{
	if (ldv_spin > 0) {
		/* ASSERT __GFP_WAIT flag should be unset (GFP_ATOMIC or GFP_NOWAIT flag should be used) when spinlock is aquired */
		ldv_assert("linux:alloc:spin lock:wrong flags", CHECK_WAIT_FLAGS(flags));
	}
}

/* MODEL_FUNC_DEF Check that spinlock is not acquired */
void ldv_check_alloc_nonatomic(void)
{
	/* ASSERT Spinlock should not be acquired */
	ldv_assert("linux:alloc:spin lock:nonatomic", ldv_spin == 0);
}

/* TODO: merge it with linux:spinlock:as. */

/* MODEL_FUNC_DEF Acquire spinlock */
void ldv_spin_lock(void)
{
	/* CHANGE_STATE Acquire spinlock () */
	ldv_spin++;
}

/* MODEL_FUNC_DEF Release spinlock */
void ldv_spin_unlock(void)
{
	/* OTHER Do not consider executions on error pathes */
	ldv_assume(ldv_spin >= 1); // TODO: it must be tested with 39 in MAV
	/* CHANGE_STATE Release spinlock */
	ldv_spin--;
}

/* MODEL_FUNC_DEF Try to acquire spinlock */
int ldv_spin_trylock(void)
{
	int is_lock;

	/* OTHER Nondeterministically acquire spinlock */
	is_lock = ldv_undef_int();

	if (is_lock)
	{
		/* RETURN Could not acquire spinlock */
		return 0;
	}
	else
	{
		/* CHANGE_STATE Acquire spinlock */
		ldv_spin++;
		/* RETURN Spinlock was successfully acquired */
		return 1;
	}
}
