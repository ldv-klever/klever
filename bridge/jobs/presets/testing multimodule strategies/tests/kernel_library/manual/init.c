#include <linux/module.h>

extern int export_with_error(void);

static int __init init(void)
{
	export_with_error();
	return 0;
}

module_init(init);
