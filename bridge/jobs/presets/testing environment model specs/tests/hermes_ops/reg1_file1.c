#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/mutex.h>
#include "orinoco.h"

struct mutex *ldv_envgen;
static int ldv_function(void);
struct usb_interface *interface;
const struct usb_device_id *id;

void ezusb_disconnect(struct usb_interface *intf);
int ezusb_probe(struct usb_interface *interface,
		       const struct usb_device_id *id);

static int hermes_init(struct hermes *hw)
{
	mutex_lock(ldv_envgen);
	mutex_lock(ldv_envgen);
}

static const struct hermes_ops ldv_ops = {
	.init = hermes_init
};

static int __init ldv_init(void)
{
	int res = ezusb_probe(interface , id);
	return res;
}

static void __exit ldv_exit(void)
{
	ezusb_disconnect(interface);
}

module_init(ldv_init);
module_exit(ldv_exit);