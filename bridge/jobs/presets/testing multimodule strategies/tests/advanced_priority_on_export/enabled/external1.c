#include <linux/module.h>
#include <linux/mutex.h>

extern void bad_export(void);

static int __init exinit1(void)
{
	return 0;
}

module_init(exinit1);