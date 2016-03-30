#include <verifier/rcv.h>
#include <verifier/map.h>

struct usb_device;

ldv_map LDV_USB_DEV_REF_COUNTS;

/* MODEL_FUNC_DEF Increment USB device reference counter */
void ldv_usb_get_dev(struct usb_device *dev)
{
    /* OTHER Whether USB device is not NULL */
    if (dev) {
	    /* CHANGE_STATE Increment USB device reference counter */
        ldv_map_put(LDV_USB_DEV_REF_COUNTS, dev,
                    ldv_map_contains_key(LDV_USB_DEV_REF_COUNTS, dev)
                    ? ldv_map_get(LDV_USB_DEV_REF_COUNTS, dev) + 1
                    : 1);
    }

	/* RETURN USB device */
	return dev;
}

/* MODEL_FUNC_DEF Check that USB device reference counter was incremented and decrement it */
void ldv_usb_put_dev(struct usb_device *dev)
{
    /* OTHER Whether USB device is not NULL */
    if (dev) {
        /* ASSERT USB device reference counter must be incremented */
        ldv_assert("linux:usb:resource:ref:unincremented counter decrement", ldv_map_contains_key(LDV_USB_DEV_REF_COUNTS, dev));
        /* ASSERT USB device reference counter must be incremented */
        ldv_assert("linux:usb:resource:ref:less initial decrement", ldv_map_get(LDV_USB_DEV_REF_COUNTS, dev) > 0);
        /* CHANGE_STATE Decrement USB device reference counter */
        ldv_map_get(LDV_USB_DEV_REF_COUNTS, dev) > 1
            ? ldv_map_put(LDV_USB_DEV_REF_COUNTS, dev, ldv_map_get(LDV_USB_DEV_REF_COUNTS, dev) - 1)
            : ldv_map_remove(LDV_USB_DEV_REF_COUNTS, dev);
	}
}

/* TODO: EMG doesn't support this now. */
/* MODEL_FUNC_DEF Check that probe() keeps model in proper state */
void ldv_check_return_value_probe(int retval)
{
	/* OTHER probe() finished unsuccessfully and returned error code */
	if (retval)
	{
		/* ASSERT USB device reference counter should not be increased */
		ldv_assert("", ldv_map_is_empty(LDV_USB_DEV_REF_COUNTS));
	}
}

/* MODEL_FUNC_DEF Initialize all USB device reference counters at the beginning */
void ldv_initialize(void)
{
	/* CHANGE_STATE All USB device reference counters aren't incremented at the beginning */
	ldv_map_init(LDV_USB_DEV_REF_COUNTS);
}

/* MODEL_FUNC_DEF Check that all USB device reference counters are not incremented at the end */
void ldv_check_final_state(void)
{
	/* ASSERT All incremented USB device reference counters must be decremented at the end */
	ldv_assert("linux:usb:resource:ref:more initial at exit", ldv_map_is_empty(LDV_USB_DEV_REF_COUNTS));
}
