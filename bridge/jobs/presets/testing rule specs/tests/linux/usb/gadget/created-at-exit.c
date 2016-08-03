#include <linux/module.h>
#include <linux/device.h>

static int __init init(void)
{
	struct class *res;
	res = class_create(THIS_MODULE, "test");
	return 0;
}

module_init(init);
