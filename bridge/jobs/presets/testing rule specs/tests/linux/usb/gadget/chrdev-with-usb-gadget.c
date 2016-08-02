#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/fs.h>
#include <linux/usb/gadget.h>

static int __init init(void)
{
	dev_t *dev;
	unsigned int baseminor, count;
	struct usb_gadget_driver *cur_driver;

	if (!usb_gadget_probe_driver(cur_driver)) {
		if (!alloc_chrdev_region(dev, baseminor, count, "test__")) {
			usb_gadget_unregister_driver(cur_driver);
			unregister_chrdev_region(dev, count);
		}
	}

	return 0;
}

module_init(init);
