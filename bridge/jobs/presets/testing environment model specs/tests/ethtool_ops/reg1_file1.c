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


static void get_drvinfo(struct net_device *dev, struct ethtool_drvinfo *info)
{
	mutex_lock(ldv_envgen);
}

static int get_settings(struct net_device *dev, struct ethtool_cmd *cmd)
{
	mutex_lock(ldv_envgen);
	return 0;
}

static int set_settings(struct net_device *dev, struct ethtool_cmd *cmd)
{
	mutex_lock(ldv_envgen);
	return 0;
}

static u32 get_link(struct net_device *dev)
{
	mutex_lock(ldv_envgen);
}

static struct ethtool_ops ops = {
	.get_drvinfo = get_drvinfo,
	.get_settings = get_settings,
	.set_settings = set_settings,
	.get_link = get_link,
};

static int __init ldv_init(void)
{
	SET_ETHTOOL_OPS(dev,&ops);
	return 0;
}

static void __exit ldv_exit(void)
{
	unregister_netdev(dev);
}

module_init(ldv_init);
module_exit(ldv_exit);
