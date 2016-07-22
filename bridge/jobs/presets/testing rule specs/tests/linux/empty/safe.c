#include <linux/module.h>

/* This is a safe test to verify that all headers required by models are
 * present in verification objects. The most of such headers, e.g.
 * linux/types.h, linux/gfp.h, linux/errno.h, linux/spinlock_types.h, are
 * present because of they are included from linux/module.h that is included
 * by all modules. */
int __init my_init(void)
{
	return 0;
}

module_init(my_init);
