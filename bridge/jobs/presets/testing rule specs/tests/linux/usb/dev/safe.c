#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/usb.h>

static int __init init(void)
{
	struct usb_device *udev_1;
	struct usb_device *udev_2;
	udev_1 = usb_get_dev(udev_1);
	udev_2 = usb_get_dev(udev_2);

	if (udev_1)
	{
		usb_put_dev(udev_1);
	}
	if (udev_2)
	{
		usb_put_dev(udev_2);
	}

	return 0;
}

module_init(init);
