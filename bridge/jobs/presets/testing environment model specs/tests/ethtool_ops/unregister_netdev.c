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
    int flip_a_coin;

    flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        SET_ETHTOOL_OPS(&dev, &ops);
        ldv_register();
        if (!register_netdev(&dev)) {
            unregister_netdev(&dev);
            ldv_deregister();
        }
    }
    return 0;
}

static void __exit ldv_exit(void)
{
    /* pass */
}

module_init(ldv_init);
module_exit(ldv_exit);
