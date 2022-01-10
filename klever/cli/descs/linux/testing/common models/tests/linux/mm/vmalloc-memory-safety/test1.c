#include <linux/module.h>
#include <ldv/common/test.h>
#include "alloc.h"

static int __init ldv_init(void)
{
	__ldv_alloc(1, 11);
	__ldv_alloc(2, 12);
	__ldv_alloc(3, 13);

	__ldv_alloc(5, 15);
	__ldv_alloc(6, 16);
	__ldv_alloc(7, 17);
	__ldv_alloc(8, 18);

	__ldv_alloc(11, 111);

	__ldv_alloc(16, 116);
}

module_init(ldv_init);
