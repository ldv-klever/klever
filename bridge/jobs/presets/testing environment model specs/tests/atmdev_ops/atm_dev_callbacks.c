#include <linux/module.h>
#include <linux/atmdev.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

struct atm_dev *ldv_dev;
struct device *ldv_parent;
int flip_a_coin;

static void ldv_close(struct atm_dev *dev)
{
    ldv_release_down();
    ldv_invoke_callback();
}


static int ldv_open(struct atm_vcc *vcc)
{
    int res;
    res = ldv_undef_int();

    ldv_invoke_callback();
    if (!res)
        ldv_probe_up();

    return res;
}

static struct atmdev_ops ldv_ops = {
        .open = ldv_open,
        .close = ldv_close
};

static int __init ldv_init(void)
{
    long *flags;

    flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        return atm_dev_register("ldv", ldv_parent, &ldv_ops, ldv_undef_int(), flags);
    }
    return 0;
}

static void __exit ldv_exit(void)
{
    if (flip_a_coin) {
        atm_dev_deregister(ldv_dev);
        ldv_deregister();
    }
}

module_init(ldv_init);
module_exit(ldv_exit);
