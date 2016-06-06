#include <linux/module.h>
#include "../drivers/md/md.h"
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

static int run(struct mddev *mddev)
{
	ldv_invoke_callback();
    return 0;
}

static int stop(struct mddev *mddev)
{
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
    int flip_a_coin;

	flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        if (!register_md_personality(&ldv_personality)) {
            unregister_md_personality(&ldv_personality);
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
