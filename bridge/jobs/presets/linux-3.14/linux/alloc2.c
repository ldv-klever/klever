#include <linux/types.h>
#include <linux/ldv/gfp.h>
#include <verifier/common.h>

#define LDV_ZERO_STATE 0

extern struct page *ldv_some_page(void);

/* There are 2 possible states. */
enum {
	LDV_SPIN_UNLOCKED = LDV_ZERO_STATE, /* Spinlock is not acquired. */
	LDV_SPIN_LOCKED                     /* Spinlock is acquired. */
};

/* CHANGE_STATE Spinlock is not acquired at the beginning */
int ldv_spin = LDV_SPIN_UNLOCKED;

/* MODEL_FUNC_DEF Check that correct flag was used when spinlock is aquired */
void ldv_check_alloc_flags(gfp_t flags)
{
	/* ASSERT __GFP_WAIT flag should be unset (GFP_ATOMIC or GFP_NOWAIT flag should be used) when spinlock is aquired */
	ldv_assert(ldv_spin == LDV_SPIN_UNLOCKED || CHECK_WAIT_FLAGS(flags));
}

/* MODEL_FUNC_DEF Check that spinlock is not acquired */
void ldv_check_alloc_nonatomic(void)
{
	/* ASSERT Spinlock should not be acquired */
	ldv_assert(ldv_spin == LDV_SPIN_UNLOCKED);
}

/* MODEL_FUNC_DEF Check that correct flag was used when spinlock is aquired and return some page */
struct page *ldv_check_alloc_flags_and_return_some_page(gfp_t flags)
{
	/* ASSERT __GFP_WAIT flag should be unset (GFP_ATOMIC or GFP_NOWAIT flag should be used) when spinlock is aquired */
	ldv_assert(ldv_spin == LDV_SPIN_UNLOCKED || CHECK_WAIT_FLAGS(flags));
	/* RETURN Some page (maybe NULL) */
	return ldv_some_page();
}

/* MODEL_FUNC_DEF Acquire spinlock */
void ldv_spin_lock(void)
{
	/* CHANGE_STATE Acquire spinlock */
	ldv_spin = LDV_SPIN_LOCKED;
}

/* MODEL_FUNC_DEF Release spinlock */
void ldv_spin_unlock(void)
{
	/* CHANGE_STATE Release spinlock */
	ldv_spin = LDV_SPIN_UNLOCKED;
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
		ldv_spin = LDV_SPIN_LOCKED;
		/* RETURN Spinlock was successfully acquired */
		return 1;
	}
}
