#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/fs.h>
#include <linux/usb/gadget.h>

static int __init init(void)
{
	struct module *cur_module;
	struct class *cur_class;
	dev_t *dev;
	const struct file_operations *fops;
	unsigned int baseminor, count;
	struct usb_gadget_driver *cur_driver;

	cur_class = class_create(cur_module, "test");
	if (IS_ERR(cur_class))
	{
		return -10;
	}
	class_destroy(cur_class);

	if (class_register(cur_class) == 0)
	{
		class_destroy(cur_class);
	}

	if (!alloc_chrdev_region(dev, baseminor, count, "test__"))
	{
		unregister_chrdev_region(dev, count);
	}

	if (!register_chrdev_region(dev, count, "__test"))
	{
		unregister_chrdev_region(dev, count);
	}

	if (!register_chrdev(2, "test", fops))
	{
		unregister_chrdev_region(dev, count);
	}

	if (register_chrdev(0, "test", fops) > 0)
	{
		unregister_chrdev_region(dev, count);
	}

	if (!usb_gadget_probe_driver(cur_driver))
	{
		usb_gadget_unregister_driver(cur_driver);
	}

	// All at once.
	if (class_register(cur_class) == 0)
	{
		if (!alloc_chrdev_region(dev, baseminor, count, "test__"))
		{
			if (!usb_gadget_probe_driver(cur_driver))
			{
				usb_gadget_unregister_driver(cur_driver);
			}
			unregister_chrdev_region(dev, count);
		}
		class_destroy(cur_class);
	}

	return 0;
}

module_init(init);
