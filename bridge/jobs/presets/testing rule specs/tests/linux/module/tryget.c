#include <linux/module.h>
#include <linux/mutex.h>

static int __init init(void)
{
	struct module *test_module_1;
	struct module *test_module_2;

	try_module_get(test_module_1);
	try_module_get(test_module_2);
	module_put(test_module_2);
	module_put(test_module_1);
	return 0;
}

module_init(init);
