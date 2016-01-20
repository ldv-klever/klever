#include <verifier/rcv.h>

/* There are 2 possible states of USB device reference counters. */
enum
{
	LDV_USB_DEV_ZERO_STATE = 0, /* USB device reference hasn't been acquired. */
	LDV_USB_DEV_INCREASED = 1   /* USB device reference counter increased. */
};

/* OTHER Model automaton state (one of two possible ones) */
int ldv_usb_dev_state = LDV_USB_DEV_ZERO_STATE;

/* MODEL_FUNC_DEF Change state after increasing reference counter with usb_get_dev() */
void ldv_usb_get_dev(void)
{
	/* CHANGE_STATE Increase reference counter */
	ldv_usb_dev_state++;
}

/* MODEL_FUNC_DEF Check that USB device reference counter has been increased and change state after decreasing reference counter with usb_put_dev() */
void ldv_usb_put_dev(void)
{
	/* ASSERT USB device reference counter should be increased */
	ldv_assert(ldv_usb_dev_state >= LDV_USB_DEV_INCREASED);
	/* CHANGE_STATE Decrease reference counter */
	ldv_usb_dev_state--;
}

/* MODEL_FUNC_DEF Check that probe() keeps model in proper state */
void ldv_check_return_value_probe(int retval)
{
	/* OTHER probe() finished unsuccessfully and returned error code */
	if (retval)
	{
		/* ASSERT USB device reference counter should not be increased */
		ldv_assert(ldv_usb_dev_state < LDV_USB_DEV_INCREASED);
	}
}

/* MODEL_FUNC_DEF Check that USB device reference isn't acquired at the end */
void ldv_check_final_state(void)
{
	/* ASSERT Acquired USB device reference should be released before finishing operation */
	ldv_assert(ldv_usb_dev_state < LDV_USB_DEV_INCREASED);
}
