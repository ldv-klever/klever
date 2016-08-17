#include <linux/module.h>
#include <linux/netdevice.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

struct net_device dev;
int flip_a_coin;

static int set_settings(struct net_device *dev, struct ethtool_cmd *cmd)
{
    ldv_invoke_callback();
    return 0;
}

static struct ethtool_ops ops = {
    .set_settings = set_settings
};

static int __init ldv_init(void)
{
    flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        netdev_set_default_ethtool_ops(&dev, &ops);
        ldv_register();
        return register_netdev(&dev);
    }
    return 0;
}

static void __exit ldv_exit(void)
{
    if (flip_a_coin) {
        unregister_netdev(&dev);
        ldv_deregister();
    }
}

module_init(ldv_init);
module_exit(ldv_exit);
