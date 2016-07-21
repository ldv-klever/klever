#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/usb.h>
#include <linux/netdevice.h>


static int ldv_usb_probe(struct usb_interface *interface,
                         const struct usb_device_id *id)
{
	int err;
	struct usb_driver *ldv_usb_driver2;
	struct net_device *ldv_net_device;

	if (usb_register(ldv_usb_driver2) < 0) {
		return -1;
	}

	err = register_netdev(ldv_net_device);
	if (err < 0) {
		return err;
	}

	return 0;
}

static const struct usb_driver ldv_usb_driver = {
	.probe = ldv_usb_probe
};

static int __init init(void)
{
	return usb_register(&ldv_usb_driver);
}

module_init(init);
