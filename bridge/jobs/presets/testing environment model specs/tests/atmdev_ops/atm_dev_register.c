#include <linux/module.h>
#include <linux/atmdev.h>
#include <verifier/nondet.h>
#include <linux/emg/test_model.h>

struct atm_dev *ldv_dev;
struct device *ldv_parent;

static void ldv_close(struct atm_dev *dev)
{
    ldv_invoke_callback();
}


static int ldv_open(struct atm_vcc *vcc)
{
    ldv_invoke_callback();
}

static struct atmdev_ops ldv_ops = {
        .open		= ldv_open,
        .close		= ldv_close
};

static int __init ldv_init(void)
{
    int res;
    res = ldv_undef_int();
    if (!res) {
        ldv_register();
        return atm_dev_register("ldv", ldv_parent, &ldv_ops, number, flags);
    }

    return 0;
}

static void __exit ldv_exit(void)
{
    atm_dev_deregister(ldv_dev);
    ldv_deregister();
}

module_init(ldv_init);
module_exit(ldv_exit);
