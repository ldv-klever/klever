#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/fs.h>
#include <linux/usb/gadget.h>

static int __init init(void)
{
	dev_t *dev;
	unsigned int baseminor, count;

	alloc_chrdev_region(dev, baseminor, count, "test__");

	return 0;
}

module_init(init);
