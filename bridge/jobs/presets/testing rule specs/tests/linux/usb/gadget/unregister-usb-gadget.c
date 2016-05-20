#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/fs.h>
#include <linux/usb/gadget.h>

struct module;
struct class;
struct file_operations;
struct usb_gadget_driver;

static int __init init(void)
{
	struct module *cur_module;
	struct class *cur_class;
	dev_t *dev;
	const struct file_operations *fops;
	unsigned int baseminor, count;
	struct usb_gadget_driver *cur_driver;

	usb_gadget_unregister_driver(cur_driver);

	return 0;
}

module_init(init);
