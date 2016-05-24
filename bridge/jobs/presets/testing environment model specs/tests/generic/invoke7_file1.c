#include <linux/module.h>
#include <linux/init.h>
#include "header.h"

struct mutex *ldv_envgen;

static int __init ldv_init(void)
{
	int err;
	err = ldv_function();
	return err;
}

static void __exit ldv_exit(void)
{
	//nothing
}

module_init(ldv_init);
module_exit(ldv_exit);
