#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/fs.h>
#include <linux/usb/gadget.h>

static int __init init(void)
{
	struct usb_gadget_driver *cur_driver;

	if (usb_gadget_probe_driver(cur_driver))
	{
		usb_gadget_unregister_driver(cur_driver);
	}

	return 0;
}

module_init(init);
