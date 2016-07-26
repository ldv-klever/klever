#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/usb.h>
#include <linux/device.h>

struct device *dev;

static void get(void)
{
	struct usb_device *udev = (struct usb_device *)dev_get_drvdata(dev);
	usb_put_dev(udev);
}

static int set(void)
{
	struct usb_device *udev;
	udev = usb_get_dev(udev);
	if (dev_set_drvdata(dev, udev))
		return -1;
}

static int __init init(void)
{
	struct usb_device *udev_1;
	struct usb_device *udev_2;
	udev_1 = usb_get_dev(udev_1);
	udev_2 = usb_get_dev(udev_2);

	if (udev_1) {
		usb_put_dev(udev_1);
	}

	if (udev_2) {
		usb_put_dev(udev_2);
	}

	if (!dev || !dev->p)
		return -1;
	if (set())
	    return -1;
	get();

	return 0;
}

module_init(init);
