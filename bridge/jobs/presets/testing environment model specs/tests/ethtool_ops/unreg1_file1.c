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
int deg_lock;

struct ldvdriver {
	void (*handler)(void);
};


static void get_drvinfo(struct net_device *dev, struct ethtool_drvinfo *info)
{
	if(deg_lock){
		mutex_lock(ldv_envgen);
	}
}

static int get_settings(struct net_device *dev, struct ethtool_cmd *cmd)
{
	if(deg_lock){
		mutex_lock(ldv_envgen);
	}
	return 0;
}

static int set_settings(struct net_device *dev, struct ethtool_cmd *cmd)
{
	if(deg_lock){
		mutex_lock(ldv_envgen);
	}
	return 0;
}

static u32 get_link(struct net_device *dev)
{
	if(deg_lock){
		mutex_lock(ldv_envgen);
	}
}

static const struct ethtool_ops ops = {
	.get_drvinfo = get_drvinfo,
	.get_settings = get_settings,
	.set_settings = set_settings,
	.get_link = get_link,
};

static void handler(void)
{
	unregister_netdev(dev);
	deg_lock = 1;
};

static struct ldvdriver driver = {
	.handler =	handler
};

static int __init ldv_init(void)
{
	deg_lock = 0;
	SET_ETHTOOL_OPS(dev,&ops);
	int err;
	err = register_netdev(dev);
	if (err) {
		return err;
	}
	return 0;
}

static void __exit ldv_exit(void)
{
	//nothing
}

module_init(ldv_init);
module_exit(ldv_exit);
