#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/gfp.h>
#include <linux/usb.h>
#include <linux/usb/cdc.h>
#include <linux/netdevice.h>
#include <linux/if_arp.h>
#include <linux/if_phonet.h>
#include <linux/phonet.h>

struct mutex *ldv_envgen;
static int ldv_function(void);

struct ldv_dev {
	struct net_device	*dev;

	struct usb_interface	*intf, *data_intf;
	struct usb_device	*usb;
	unsigned int		tx_pipe, rx_pipe;
	u8 active_setting;
	u8 disconnected;

	unsigned		tx_queue;
	spinlock_t		tx_lock;

	spinlock_t		rx_lock;
	struct sk_buff		*rx_skb;
	struct urb		*urbs[0];
};

static struct usb_driver usbpn_driver;

int ldv_probe(struct usb_interface *intf, const struct usb_device_id *id)
{
	int ret;
	ret = ldv_function();
	if(ret){
		return ret;
	}
	mutex_lock(ldv_envgen);
	return 0;
}

static void ldv_disconnect(struct usb_interface *intf)
{
	mutex_unlock(ldv_envgen);
}

static struct usb_driver ldv_driver = {
	.name =		"ldv-test",
	.probe =	ldv_probe,
	.disconnect =	ldv_disconnect,
};

static int __init ldv_init(void)
{
	int res;
	res = usb_register(&ldv_driver);
	if(res){
		return res;
	}
	return res;
}

static void __exit ldv_exit(void)
{
	usb_deregister(&ldv_driver);
}

module_init(ldv_init);
module_exit(ldv_exit);
