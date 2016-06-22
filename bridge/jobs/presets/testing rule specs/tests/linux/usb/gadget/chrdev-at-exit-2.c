#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/fs.h>
#include <linux/usb/gadget.h>

static int __init init(void)
{
	dev_t *dev;
	const struct file_operations *fops;
	unsigned int baseminor, count;

	if (!register_chrdev(count, "test", fops)) {
		unregister_chrdev_region(dev, count);
	}

	return 0;
}

module_init(init);
