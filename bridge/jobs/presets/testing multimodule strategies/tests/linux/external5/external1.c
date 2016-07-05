#include <linux/module.h>
#include <linux/mutex.h>

extern void bad_export(void);

static int __init init1(void)
{
	bad_export();
	return 0;
}

module_init(init1);