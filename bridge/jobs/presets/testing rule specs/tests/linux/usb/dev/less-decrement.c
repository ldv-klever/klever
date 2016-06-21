#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/usb.h>

static int __init init(void)
{
	struct usb_device *udev_1;

	if (udev_1) {
		usb_put_dev(udev_1);
	}

	return 0;
}

module_init(init);
