#include <linux/module.h>
#include <linux/usb.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

static struct urb u;

static void ldv_handler(struct urb *u)
{
	ldv_invoke_reached();
	ldv_check_resource1(u, 0);
}

static int __init ldv_init(void)
{
	int interval = ldv_undef_int();
	void *context = ldv_undef_ptr();
	int buffer_length = ldv_undef_int();
	unsigned int pipe = ldv_undef_uint();
	void *transfer_buffer = ldv_undef_ptr();
	struct usb_device *dev = ldv_undef_ptr();
	ldv_invoke_test();
	usb_fill_int_urb(&u, dev, pipe, transfer_buffer, buffer_length,
		(usb_complete_t) ldv_handler, context, interval);
	ldv_store_resource1(&u);
	usb_submit_urb(&u, GFP_KERNEL);
	usb_unlink_urb(&u);
	return 0;
}

static void __exit ldv_exit(void) {}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");