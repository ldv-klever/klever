#include <linux/module.h>
#include <linux/mutex.h>

static int __init init(void)
{
	struct module *test_module_1;
	struct module *test_module_2;

	if (try_module_get(test_module_1))
	{
		if (try_module_get(test_module_2))
		{
			module_put(test_module_2);
		}
		module_put(test_module_1);
	}

	__module_get(test_module_1);
	module_put(test_module_1);

	if (test_module_2 != NULL)
	{
		__module_get(test_module_2);
		__module_get(test_module_2);
		module_put_and_exit(0x0);
		module_put(test_module_2);
		module_put(test_module_2);
		module_put(test_module_2);
	}

	if (test_module_1 != NULL)
	{
		__module_get(test_module_1);
		__module_get(test_module_1);
		if (module_refcount(test_module_1) == 2)
		{
			module_put(test_module_1);
			module_put(test_module_1);
		}
	}

	return 0;
}

module_init(init);
