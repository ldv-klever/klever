#include <linux/module.h>
#include <verifier/nondet.h>
#include <linux/emg/test_model.h>
#include "ldvops.h"

int flip_a_coin;

int ldv_probe(struct ldv_resource *arg)
{
    int res;

    ldv_invoke_callback();
    res = ldv_undef_int();
    if (!res)
        ldv_probe_up();
    return res;
}

void ldv_disconnect(struct ldv_resource *arg)
{
    ldv_release_down();
    ldv_invoke_callback();
}

static struct ldv_driver ops = {
	.probe = & ldv_probe,
	.disconnect = & ldv_disconnect
};

int __init ldv_init(void)
{
    flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        return ldv_driver_register(& ops);
    }
    return 0;
}

void __exit ldv_exit(void)
{
	if (flip_a_coin) {
        ldv_driver_deregister(& ops);
        ldv_deregister();
    }
}

module_init(ldv_init);
module_exit(ldv_exit);
