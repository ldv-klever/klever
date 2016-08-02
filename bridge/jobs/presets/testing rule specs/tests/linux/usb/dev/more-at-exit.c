#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/usb.h>

static int __init init(void)
{
	struct usb_device *udev;

	udev = usb_get_dev(udev);

	return 0;
}

module_init(init);
