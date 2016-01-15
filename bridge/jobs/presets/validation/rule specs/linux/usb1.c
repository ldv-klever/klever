#include <verifier/rcv.h>

/* There are 3 possible states of usb device reference counter. */
enum
{
	LDV_USB_DEV_ZERO_STATE = 0, /* Usb device reference hasn't been acquired. */
	LDV_USB_DEV_INCREASED = 1   /* Usb device reference counter increased. */
};

/* OTHER The model automaton state (one of thee possible ones) */
int ldv_usb_dev_state = LDV_USB_DEV_ZERO_STATE;

/* MODEL_FUNC_DEF Change state after increasing the reference counter with usb_get_dev */
void ldv_usb_get_dev(void)
{
	/* CHANGE_STATE Increase reference counter */
	ldv_usb_dev_state++;
}

/* MODEL_FUNC_DEF Change state after decreasing the reference counter with usb_put_dev */
void ldv_usb_put_dev(void)
{
	/* ASSERT Check usb device reference counter has been increased */
	ldv_assert(ldv_usb_dev_state >= LDV_USB_DEV_INCREASED);
	/* CHANGE_STATE Decrease reference counter */
	ldv_usb_dev_state--;
}

/* MODEL_FUNC_DEF Check the probe function leaved the model in the proper state */
void ldv_check_return_value_probe(int retval)
{
	/* OTHER Probe finished unsuccessfully and returned an error */
	if (retval) {
		/* ASSERT Check usb device reference counter is not increased */
		ldv_assert(ldv_usb_dev_state < LDV_USB_DEV_INCREASED);
	}
}

/* MODEL_FUNC_DEF Check that usb device reference hasn't been acquired or the counter has been decreased */
void ldv_check_final_state(void)
{
	/* ASSERT Check that usb device reference hasn't been acquired or the counter has been decreased */
	ldv_assert(ldv_usb_dev_state < LDV_USB_DEV_INCREASED);
}
