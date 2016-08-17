#include <linux/module.h>
#include <linux/device-mapper.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

int flip_a_coin;

static int ldv_ctr(struct dm_target *ti, unsigned int argc, char **argv)
{
	int res;

    ldv_invoke_callback();
    res = ldv_undef_int();
    if (!res)
        ldv_probe_up();
    return res;
}

static void ldv_dtr(struct dm_target *ti)
{
	ldv_release_down();
    ldv_invoke_callback();
}

static struct target_type ldv_target = {
	.name	     = "ldv",
	.module      = THIS_MODULE,
	.ctr	     = ldv_ctr,
	.dtr	     = ldv_dtr,
};

static int __init ldv_init(void)
{
	flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        return dm_register_target(&ldv_target);
    }
    return 0;
}

static void __exit ldv_exit(void)
{
	if (flip_a_coin) {
        dm_unregister_target(&ldv_target);
        ldv_deregister();
    }
}

module_init(ldv_init);
module_exit(ldv_exit);
