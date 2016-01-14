/* Here is the definition of CHECK_WAIT_FLAGS(flags) macro. */
#include "gfp.h"
#include <linux/gfp.h>
#include <verifier/rcv.h>

#define LDV_ZERO_STATE 0


/* There are 2 possible states of spin lock */
enum {
	LDV_SPIN_UNLOCKED = LDV_ZERO_STATE, /* Spin isn't locked */
	LDV_SPIN_LOCKED                     /* Spin is locked */
};


/* Spin isn't locked at the beginning */
int ldv_spin = LDV_SPIN_UNLOCKED;


/* MODEL_FUNC_DEF Check that a memory allocating function was called with a correct value of flags in spin locking */
void ldv_check_alloc_flags(gfp_t flags)
{
	/* ASSERT If spin is locked (ldv_spin != LDV_SPIN_UNLOCKED) then a memory allocating function should be called with __GFP_WAIT flag unset (GFP_ATOMIC or GFP_NOWAIT) */
	ldv_assert(ldv_spin == LDV_SPIN_UNLOCKED || CHECK_WAIT_FLAGS(flags));
}

extern struct page *ldv_some_page(void);

/* MODEL_FUNC_DEF Check that a memory allocating function was called with a correct value of flags in spin locking */
struct page *ldv_check_alloc_flags_and_return_some_page(gfp_t flags)
{
	/* ASSERT If spin is locked (ldv_spin != LDV_SPIN_UNLOCKED) then a memory allocating function should be called with __GFP_WAIT flag unset (GFP_ATOMIC or GFP_NOWAIT) */
	ldv_assert(ldv_spin == LDV_SPIN_UNLOCKED || CHECK_WAIT_FLAGS(flags));
	/* RETURN Return a page pointer (maybe NULL) */
	return ldv_some_page();
}

/* MODEL_FUNC_DEF Check that a memory allocating function was not calledin spin locking */
void ldv_check_alloc_nonatomic(void)
{
	/* ASSERT If spin is locked (ldv_spin != LDV_SPIN_UNLOCKED) then the memory allocating function should be called, because it implicitly uses GFP_KERNEL flag */
	ldv_assert(ldv_spin == LDV_SPIN_UNLOCKED);
}

/* MODEL_FUNC_DEF Lock spin */
void ldv_spin_lock(void)
{
	/* CHANGE_STATE Lock spin */
	ldv_spin = LDV_SPIN_LOCKED;
}

/* MODEL_FUNC_DEF Unlock spin */
void ldv_spin_unlock(void)
{
	/* CHANGE_STATE Unlock spin */
	ldv_spin = LDV_SPIN_UNLOCKED;
}

/* MODEL_FUNC_DEF Try to lock spin. It should return 0 if spin wasn't locked */
int ldv_spin_trylock(void)
{
	int is_lock;

	/* LDV_COMMENT_OTHER Do this to make nondetermined choice */
	is_lock = ldv_undef_int();

	if (is_lock)
	{
		/* RETURN Don't lock spin and return 0 */
		return 0;
	}
	else
	{
		/* CHANGE_STATE Lock spin */
		ldv_spin = LDV_SPIN_LOCKED;
		/* RETURN Return 1 since spin was locked */
		return 1;
	}
}
