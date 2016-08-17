#include <linux/module.h>
#include <verifier/nondet.h>
#include <linux/emg/test_model.h>
#include "ldvops.h"

int ldv_driver_array_register(struct ldv_driver **ops);
void ldv_driver_array_deregister(struct ldv_driver **ops);

void handler1(struct ldv_resource *arg)
{
    ldv_invoke_reached();
}

void handler2(struct ldv_resource *arg)
{
    ldv_invoke_reached();
}

static struct ldv_driver ops[2] = {
	{
	    .handler = & handler1
	},
	{
	    .handler = & handler2
	}
};

static int __init ldv_init(void)
{
	return ldv_driver_array_register(& ops);
}

static void __exit ldv_exit(void)
{
	ldv_driver_array_deregister(& ops);
}

module_init(ldv_init);
module_exit(ldv_exit);
