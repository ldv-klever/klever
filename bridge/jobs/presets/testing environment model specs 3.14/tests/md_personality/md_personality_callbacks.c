#include <linux/module.h>
#include "../drivers/md/md.h"
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

int flip_a_coin;

static int run(struct mddev *mddev)
{
	int res;

    ldv_invoke_callback();
    res = ldv_undef_int();
    if (!res)
        ldv_probe_up();
    return res;
}

static int stop(struct mddev *mddev)
{
	ldv_release_down();
    ldv_invoke_callback();
    return 0;
}

static struct md_personality ldv_personality =
{
	.name		= "ldv",
	.run		= run,
	.stop		= stop,
};

static int __init ldv_init(void)
{
	flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        return register_md_personality(&ldv_personality);
    }
    return 0;
}

static void __exit ldv_exit(void)
{
	if (flip_a_coin) {
        unregister_md_personality(&ldv_personality);
        ldv_deregister();
    }
}

module_init(ldv_init);
module_exit(ldv_exit);
