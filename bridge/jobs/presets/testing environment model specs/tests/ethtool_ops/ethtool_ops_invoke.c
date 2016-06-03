#include <linux/module.h>
#include <linux/netdevice.h>
#include <linux/ethtool.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

struct net_device dev;

static int set_settings(struct net_device *dev, struct ethtool_cmd *cmd)
{
    ldv_invoke_reached();
    return 0;
}

static struct ethtool_ops ops = {
    .set_settings = set_settings
};

static int __init ldv_init(void)
{
    ldv_register();
    SET_ETHTOOL_OPS(&dev, &ops);
    return register_netdev(&dev);
}

static void __exit ldv_exit(void)
{
    unregister_netdev(&dev);
    ldv_deregister();
}

module_init(ldv_init);
module_exit(ldv_exit);
