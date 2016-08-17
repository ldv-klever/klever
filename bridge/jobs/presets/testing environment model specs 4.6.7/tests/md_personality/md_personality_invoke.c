#include <linux/module.h>
#include "../drivers/md/md.h"
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

static int ldv_run(struct mddev *mddev)
{
	ldv_invoke_reached();
	return 0;
}

static void md_free(struct mddev *mddev, void *priv)
{
	ldv_invoke_reached();
	return 0;
}

static struct md_personality ldv_personality =
{
	.name		= "ldv",
	.run		= ldv_run,
	.free		= md_free,
};

static int __init ldv_init(void)
{
	return register_md_personality(&ldv_personality);
}

static void __exit ldv_exit(void)
{
    unregister_md_personality(&ldv_personality);
}

module_init(ldv_init);
module_exit(ldv_exit);
