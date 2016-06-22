#include <linux/module.h>
#include <verifier/nondet.h>
#include <linux/emg/test_model.h>
#include "ldvops.h"

int ldv_probe(struct ldv_resource *arg)
{
    ldv_invoke_callback();
    return 0;
}

void ldv_disconnect(struct ldv_resource *arg)
{
    ldv_invoke_callback();
}

static struct ldv_driver ops = {
	.probe = ldv_probe,
	.disconnect = ldv_disconnect
};

static int __init ldv_init(void)
{
    int flip_a_coin;

    flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        if (!ldv_driver_register(& ops)) {
            ldv_driver_deregister(& ops);
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
