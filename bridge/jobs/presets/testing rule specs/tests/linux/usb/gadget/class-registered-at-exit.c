#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/fs.h>
#include <linux/usb/gadget.h>

static int __init init(void)
{
	struct class *cur_class;

	class_register(cur_class);

	return 0;
}

module_init(init);
