#include <linux/module.h>
#include <linux/device-mapper.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

static int ldv_ctr(struct dm_target *ti, unsigned int argc, char **argv)
{
	ldv_invoke_reached();
    return 0;
}

static void ldv_dtr(struct dm_target *ti)
{
	ldv_invoke_reached();
}

static struct target_type ldv_target = {
	.name	     = "ldv",
	.module      = THIS_MODULE,
	.ctr	     = ldv_ctr,
	.dtr	     = ldv_dtr,
};

static int __init ldv_init(void)
{
	dm_register_target(&ldv_target);
}

static void __exit ldv_exit(void)
{
	dm_unregister_target(&ldv_target);
}

module_init(ldv_init);
module_exit(ldv_exit);
