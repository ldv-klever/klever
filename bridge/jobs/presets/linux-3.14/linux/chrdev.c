#include <linux/ldv/common.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

/* There are 2 possible states of char device region registration. */
enum
{
	LDV_CHRDEV_ZERO_STATE, /* Char device region is not registered for usb gadget. */
	LDV_CHRDEV_REGISTERED  /* Char device region is registered for usb gadget. */
};

/* CHANGE_STATE Char device region is not registered at the beginning */
int ldv_usb_gadget_chrdev = LDV_CHRDEV_ZERO_STATE;

/* MODEL_FUNC_DEF Check that chrdev region was not registered and register it */
int ldv_register_chrdev(int major)
{
	int is_reg;

	/* OTHER Register chrdev in the nondeterministic way */
	is_reg = ldv_undef_int_nonpositive();

	/* ASSERT Register chrdev just in case when an error did not happen */
	if (!is_reg) {
		/* ASSERT Check that chrdev region is unregistered */
		ldv_assert("linux:chrdev:double registration", ldv_usb_gadget_chrdev == LDV_CHRDEV_ZERO_STATE);
		/* CHANGE_STATE Register chrdev region for usb gadget */
		ldv_usb_gadget_chrdev = LDV_CHRDEV_REGISTERED;
		if (major == 0) {
			/* OTHER Function returns allocated major number */
			is_reg = ldv_undef_int();
			ldv_assume (is_reg > 0);
		}
	}

	/* RETURN Return registration status (0 is success) */
	return is_reg;
}

/* MODEL_FUNC_DEF Check that chrdev region was not registered and register it */
int ldv_register_chrdev_region(void)
{
	int is_reg;

	/* OTHER Register chrdev in the nondeterministic way */
	is_reg = ldv_undef_int_nonpositive();

	/* ASSERT Register chrdev just in case when an error did not happen */
	if (!is_reg) {
		/* ASSERT Check that chrdev region is unregistered */
		ldv_assert("linux:chrdev:double registration", ldv_usb_gadget_chrdev == LDV_CHRDEV_ZERO_STATE);
		/* CHANGE_STATE Register chrdev region for usb gadget */
		ldv_usb_gadget_chrdev = LDV_CHRDEV_REGISTERED;
	}

	/* RETURN Return registration status (0 is success) */
	return is_reg;
}

/* MODEL_FUNC_DEF Check that chrdev region was registered and unregister it */
void ldv_unregister_chrdev_region(void)
{
	/* ASSERT Check that chrdev region is registered */
	ldv_assert("linux:chrdev:double deregistration", ldv_usb_gadget_chrdev == LDV_CHRDEV_REGISTERED);
	/* CHANGE_STATE Unregister chrdev */
	ldv_usb_gadget_chrdev = LDV_CHRDEV_ZERO_STATE;
}

/* MODEL_FUNC_DEF Check that usb gadget is fully unregistered at the end */
void ldv_check_final_state(void)
{
	/* ASSERT Chrdev region should be unregistered at the end */
	ldv_assert("linux:chrdev:registered at exit", ldv_usb_gadget_chrdev == LDV_CHRDEV_ZERO_STATE);
}
