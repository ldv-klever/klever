#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/major.h>
#include <linux/usb.h>
#include <linux/netdevice.h>


static int usb_ldv_dummy_probe(struct usb_interface *interface,
                               const struct usb_device_id *id);

static void usb_ldv_dummy_disconnect(struct usb_interface *interface);

static const struct usb_device_id id_table[] = {
	{ } /* Terminating entry */
};

static const struct usb_driver ldv_dummy_driver = {
	.name =       "probe_retval_check",
	.probe =      usb_ldv_dummy_probe,
	.disconnect = usb_ldv_dummy_disconnect,
	.id_table =   id_table,
};

static int __init init(void)
{
	return usb_register(&ldv_dummy_driver);
}

/* This function are defined here just to make Driver Environment Generator
 * produce their calls. So corresponding test case functions are called too.
 */
static int usb_ldv_dummy_probe(struct usb_interface *interface,
                               const struct usb_device_id *id)
{
	struct net_device *dummy_net_device;

	int ret = register_netdev(dummy_net_device);
	return 0;

}

static void usb_ldv_dummy_disconnect(struct usb_interface *interface)
{
}

module_init(init);
