#include <linux/kernel.h>
#include <linux/mm.h>
#include <linux/module.h>
#include <linux/gfp.h>
#include <linux/usb.h>
#include <linux/usb/cdc.h>
#include <linux/netdevice.h>
#include <linux/if_arp.h>
#include <linux/if_phonet.h>
#include <linux/phonet.h>

struct net_device *dev;
struct mutex *ldv_envgen;
static int ldv_function(void);

/*
 * Network device callbacks
 */
static netdev_tx_t ldv_xmit(struct sk_buff *skb, struct net_device *dev);

static int ldv_open(struct net_device *dev)
{
	int err;
	err = ldv_function();
	if(err){
		return err;
	}
	mutex_lock(ldv_envgen);
	return 0;
}

static int ldv_close(struct net_device *dev)
{
	mutex_unlock(ldv_envgen);
}

static int ldv_ioctl(struct net_device *dev, struct ifreq *ifr, int cmd);

static int ldv_set_mtu(struct net_device *dev, int new_mtu);

static const struct net_device_ops ldv_ops = {
	.ndo_open	= ldv_open,
	.ndo_stop	= ldv_close,
	.ndo_start_xmit = ldv_xmit,
	.ndo_do_ioctl	= ldv_ioctl,
	.ndo_change_mtu = ldv_set_mtu,
};

static int __init ldv_init(void)
{
	int err;
	err = register_netdev(dev);
	if (err) {
		return err;
	}
	return 0;
}

static void __exit ldv_exit(void)
{
	unregister_netdev(dev);
}

module_init(ldv_init);
module_exit(ldv_exit);
