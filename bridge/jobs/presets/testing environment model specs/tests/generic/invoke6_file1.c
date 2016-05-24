#include <linux/module.h>
#include <linux/init.h>

int ldv_main_function(void);

static int __init ldv_init(void)
{
	int err;
	err = ldv_main_function();
	return err;
}

static void __exit ldv_exit(void)
{
	//nothing
}

module_init(ldv_init);
module_exit(ldv_exit);
