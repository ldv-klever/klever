#include <linux/module.h>
#include <linux/usb.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

static struct urb u;

static void ldv_handler(struct urb *u)
{
	ldv_invoke_reached();
}

static int __init ldv_init(void)
{
	void *context = ldv_undef_ptr();
	int buffer_length = ldv_undef_int();
	unsigned int pipe = ldv_undef_uint();
	void *transfer_buffer = ldv_undef_ptr();
	struct usb_device *dev = ldv_undef_ptr();
	unsigned char *setup_packet = (unsigned char) ldv_undef_uint();
	ldv_invoke_test();
	usb_fill_control_urb(&u, dev, pipe, setup_packet, transfer_buffer, buffer_length, 
		(usb_complete_t) ldv_handler, context);
	usb_submit_urb(&u, GFP_KERNEL);
	usb_poison_urb(&u);
	return 0;
}

static void __exit ldv_exit(void) {}

module_init(ldv_init);
module_exit(ldv_exit);