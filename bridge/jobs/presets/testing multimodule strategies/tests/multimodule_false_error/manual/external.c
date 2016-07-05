#include <linux/module.h>
#include <linux/mutex.h>

static DEFINE_MUTEX(mutex);

int export_with_error(void)
{
	return 0;
}

static int __init init1(void)
{
	return 0;
}

module_init(init1);

EXPORT_SYMBOL(export_with_error);