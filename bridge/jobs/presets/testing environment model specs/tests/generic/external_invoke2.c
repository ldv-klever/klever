#include <linux/module.h>
#include <verifier/nondet.h>
#include <linux/emg/test_model.h>
#include "ldvops.h"

void ldv_handler(struct ldv_resource *arg)
{
    ldv_invoke_reached();
}