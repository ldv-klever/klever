#include <verifier/common.h>
#include <linux/ldv/common.h>

/* There are 2 possible states of usb gadget registration. */
enum
{
	LDV_USB_GADGET_ZERO_STATE, /* Usb gadget is not registered. */
	LDV_USB_GADGET_REGISTERED  /* Usb gadget is registered. */
};

/* CHANGE_STATE Usb gadget is not registered at the beginning */
int ldv_usb_gadget = LDV_USB_GADGET_ZERO_STATE;


/* MODEL_FUNC_DEF Check that class was not registered. Then create and register class for it */
void *ldv_create_class(void)
{
	void *is_got;

	/* OTHER Get blk request in the nondeterministic way */
	is_got = ldv_undef_ptr();

	/* ASSERT Get blk request just in case when an error did not happen */
	if (!ldv_is_err(is_got)) {
		/* ASSERT Registring usb gadget class is only allowed if usb gadget is not registered */
		ldv_assert("linux:usb:gadget:class registration with usb gadget", ldv_usb_gadget == LDV_USB_GADGET_ZERO_STATE);
	}

	/* RETURN Return obtained blk request */
	return is_got;
}

/* MODEL_FUNC_DEF Check that class was not registered and register class for it */
int ldv_register_class(void)
{
	int is_reg;

	/* OTHER Register gadget class in the nondeterministic way */
	is_reg = ldv_undef_int_nonpositive();

	/* ASSERT Get blk request just in case when an error did not happen */
	if (!is_reg) {
		/* ASSERT Registering usb gadget class is only allowed if usb gadget is not registered */
		ldv_assert("linux:usb:gadget:class registration with usb gadget", ldv_usb_gadget == LDV_USB_GADGET_ZERO_STATE);
	}

	/* RETURN Return registration status (0 is success) */
	return is_reg;
}

/* MODEL_FUNC_DEF Check that class was registered and unregister it */
void ldv_unregister_class(void)
{
	/* ASSERT Unregistering usb gadget class is only allowed if usb gadget is not registered */
	ldv_assert("linux:usb:gadget:class deregistration with usb gadget", ldv_usb_gadget == LDV_USB_GADGET_ZERO_STATE);
}

/* MODEL_FUNC_DEF Check that chrdev region was not registered and register it */
int ldv_register_chrdev(int major)
{
	int is_reg;

	/* OTHER Register chrdev in the nondeterministic way */
	is_reg = ldv_undef_int_nonpositive();

	/* ASSERT Register chrdev just in case when an error did not happen */
	if (!is_reg) {
		/* ASSERT Usb gadget should be unregistered at this point */
		ldv_assert("linux:usb:gadget:chrdev registration with usb gadget", ldv_usb_gadget == LDV_USB_GADGET_ZERO_STATE);
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
		/* ASSERT Usb gadget should be unregistered at this point */
		ldv_assert("linux:usb:gadget:chrdev registration with usb gadget", ldv_usb_gadget == LDV_USB_GADGET_ZERO_STATE);
	}

	/* RETURN Return registration status (0 is success) */
	return is_reg;
}

/* MODEL_FUNC_DEF Check that chrdev region was registered and unregister it */
void ldv_unregister_chrdev_region(void)
{
	/* ASSERT Usb gadget should not be registered at this point */
	ldv_assert("linux:usb:gadget:chrdev deregistration with usb gadget", ldv_usb_gadget == LDV_USB_GADGET_ZERO_STATE);
}

/* MODEL_FUNC_DEF Check that usb gadget was not registered and register it */
int ldv_register_usb_gadget(void)
{
	int is_reg;

	/* OTHER Register usb gadget in the nondeterministic way */
	is_reg = ldv_undef_int_nonpositive();

	/* ASSERT Register usb gadget just in case when an error did not happen */
	if (!is_reg) {
		/* ASSERT Gadget should not be registered at this point */
		ldv_assert("linux:usb:gadget:double usb gadget registration", ldv_usb_gadget == LDV_USB_GADGET_ZERO_STATE);
		/* CHANGE_STATE Register usb gadget */
		ldv_usb_gadget = LDV_USB_GADGET_REGISTERED;
	}

	/* RETURN Return registration status (0 is success) */
	return is_reg;
}

/* MODEL_FUNC_DEF Check that usb gadget was registered and unregister it */
void ldv_unregister_usb_gadget(void)
{
	/* ASSERT Usb gadget should be registered at this point */
	ldv_assert("linux:usb:gadget:double usb gadget deregistration", ldv_usb_gadget == LDV_USB_GADGET_REGISTERED);
	/* CHANGE_STATE Unregister usb gadget */
	ldv_usb_gadget = LDV_USB_GADGET_ZERO_STATE;
}

/* MODEL_FUNC_DEF Check that usb gadget is fully unregistered at the end */
void ldv_check_final_state(void)
{
	/* ASSERT Usb gadget should be unregistered at the end */
	ldv_assert("linux:usb:gadget:usb gadget registered at exit", ldv_usb_gadget == LDV_USB_GADGET_ZERO_STATE);
}
