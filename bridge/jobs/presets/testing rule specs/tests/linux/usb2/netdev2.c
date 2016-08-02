#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/usb.h>
#include <linux/netdevice.h>


static int ldv_ndo_open(struct net_device *dev) {
	int err;
	struct net_device *ldv_net_device;

	err = register_netdev(ldv_net_device);

	return 0;
}

static struct net_device_ops ldv_net_device_ops = {
	.ndo_open = ldv_ndo_open
};

static struct net_device ldv_net_device = {
	.netdev_ops = &ldv_net_device_ops
};

static int ldv_usb_probe(struct usb_interface *interface,
                         const struct usb_device_id *id)
{
	return register_netdev(&ldv_net_device);
}

static struct usb_driver ldv_usb_driver = {
	.probe = ldv_usb_probe
};

static int __init init(void)
{
	return usb_register(&ldv_usb_driver);
}

module_init(init);
