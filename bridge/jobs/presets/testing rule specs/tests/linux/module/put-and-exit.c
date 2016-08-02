#include <linux/module.h>

static int __init init(void)
{
	struct module *test_module;
	__module_get(test_module);
	module_put_and_exit(0x0);
	return 0;
}

module_init(init);
