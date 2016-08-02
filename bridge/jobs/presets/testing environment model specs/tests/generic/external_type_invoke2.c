#include <linux/module.h>
#include <verifier/nondet.h>
#include <linux/emg/test_model.h>
#include "ldvops.h"

void ldv_handler(struct ldv_resource *arg)
{
    ldv_invoke_reached();
}

struct ldv_driver ops = {
	.handler = & ldv_handler,
};

int wrapper_register(void)
{
	return ldv_driver_register(& ops);
}

void wrapper_deregister(void)
{
	ldv_driver_deregister(& ops);
}