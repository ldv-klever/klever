#include <linux/kernel.h>
#include <linux/gfp.h>
#include <verifier/rcv.h>

struct page *ldv_some_page(void);

/* CHANGE_STATE Usb lock state = free */
int ldv_lock = 1;

/* MODEL_FUNC_DEF Check that a memory allocation function function was called with a correct value of flags (in usb locking) */
void ldv_check_alloc_flags(gfp_t flags) 
{
	/* ASSERT If usb lock is locked (ldv_lock = 2) then a memory allocating function should be called with flags equals to GFP_ATOMIC or GFP_NOIO */
	if (ldv_lock == 2)
	{
		ldv_assert(flags == GFP_NOIO || flags == GFP_ATOMIC);
	}
}

/* MODEL_FUNC_DEF Check that a memory allocation function function was called with a correct value of flags (in usb locking) */
void ldv_check_alloc_nonatomic(void)
{
	/* ASSERT If usb lock is locked (ldv_lock = 2) then a memory allocating function should be called with flags equals to GFP_ATOMIC or GFP_NOIO */
	if (ldv_lock == 2)
	{
		ldv_assert(0);
	}
}

/* MODEL_FUNC_DEF Check that a alloc_pages function was called with a correct value of flags (in usb locking) */
struct page *ldv_check_alloc_flags_and_return_some_page(gfp_t flags)
{
	if (ldv_lock == 2)
	{
		ldv_assert(flags == GFP_NOIO || flags == GFP_ATOMIC);
	}
	
	/* RETURN Return a page pointer (maybe NULL) */
	return ldv_some_page();
}

/* MODEL_FUNC_DEF Acquires the usb lock and checks for double usb lock */
void ldv_usb_lock_device(void)
{
	/* CHANGE_STATE Go to locked state */
	ldv_lock = 2;
}

/* MODEL_FUNC_DEF Tries to acquire the usb lock and returns 1 if successful */
int ldv_usb_trylock_device(void)
{
	if(ldv_lock == 1 && ldv_undef_int())
	{
		/* CHANGE_STATE Goto locked state */
		ldv_lock = 2;
		/* RETURN Usb lock is acquired */
		return 1;
	}
	else
	{
		/* RETURN Usb lock is not acquired */
		return 0;
	}
}

/* MODEL_FUNC_DEF Tries to acquire the usb lock and returns 0 if successful */
int ldv_usb_lock_device_for_reset(void)
{
	if(ldv_lock == 1 && ldv_undef_int())
	{
		/* CHANGE_STATE Goto locked state */
		ldv_lock = 2;
		/* RETURN Usb lock is acquired */
		return 0;
	}
	else
	{
		/* RETURN Usb lock is not acquired */
		return -1;
	}
}

/* MODEL_FUNC_DEF Releases the usb lock and checks that usb lock was acquired before */
void ldv_usb_unlock_device(void) {
	/* CHANGE_STATE Go to free state */
	ldv_lock = 1;
}
