#include <linux/module.h>
#include <linux/device-mapper.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

static int ldv_ctr(struct dm_target *ti, unsigned int argc, char **argv)
{
	ldv_invoke_callback();
    return 0;
}

static void ldv_dtr(struct dm_target *ti)
{
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
	int flip_a_coin;

	flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        if (!dm_register_target(&ldv_target)) {
            dm_unregister_target(&ldv_target);
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
