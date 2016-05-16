#include <linux/module.h>
#include <linux/mutex.h>

static int __init init(void)
{
    struct module *test_module;
    __module_get(test_module);
	return 0;
}

module_init(init);
