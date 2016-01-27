#include <linux/kernel.h>
#include <linux/gfp.h>
#include <verifier/rcv.h>

struct page *ldv_some_page(void);

/* CHANGE_STATE USB lock is not acquired at the beginning */
int ldv_lock = 1;

/* MODEL_FUNC_DEF Check that correct flag was used when USB lock is aquired */
void ldv_check_alloc_flags(gfp_t flags) 
{
	if (ldv_lock == 2)
	{
		/* ASSERT GFP_NOIO or GFP_ATOMIC flag should be used when USB lock is aquired */
		ldv_assert(flags == GFP_NOIO || flags == GFP_ATOMIC);
	}
}

/* MODEL_FUNC_DEF Check that USB lock is not acquired */
void ldv_check_alloc_nonatomic(void)
{
	if (ldv_lock == 2)
	{
		/* ASSERT USB lock should not be acquired */
		ldv_assert(0);
	}
}

/* MODEL_FUNC_DEF Check that correct flag was used when USB lock is aquired and return some page */
struct page *ldv_check_alloc_flags_and_return_some_page(gfp_t flags)
{
	if (ldv_lock == 2)
	{
		/* ASSERT GFP_NOIO or GFP_ATOMIC flag should be used when USB lock is aquired */
		ldv_assert(flags == GFP_NOIO || flags == GFP_ATOMIC);
	}
	
	/* RETURN Some page (maybe NULL) */
	return ldv_some_page();
}

/* MODEL_FUNC_DEF Acquire USB lock */
void ldv_usb_lock_device(void)
{
	/* CHANGE_STATE Acquire USB lock */
	ldv_lock = 2;
}

/* MODEL_FUNC_DEF Try to acquire USB lock */
int ldv_usb_trylock_device(void)
{
	if (ldv_lock == 1 && ldv_undef_int())
	{
		/* CHANGE_STATE Acquire USB lock */
		ldv_lock = 2;
		/* RETURN USB lock was acquired */
		return 1;
	}
	else
	{
		/* RETURN USB lock was not acquired */
		return 0;
	}
}

/* MODEL_FUNC_DEF Try to acquire USB lock */
int ldv_usb_lock_device_for_reset(void)
{
	if (ldv_lock == 1 && ldv_undef_int())
	{
		/* CHANGE_STATE Acquire USB lock */
		ldv_lock = 2;
		/* RETURN USB lock was acquired */
		return 0;
	}
	else
	{
		/* RETURN USB lock wad not acquired */
		return -1;
	}
}

/* MODEL_FUNC_DEF Release USB lock */
void ldv_usb_unlock_device(void)
{
	/* CHANGE_STATE Release USB lock */
	ldv_lock = 1;
}
