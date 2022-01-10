#include <linux/module.h>
#include <ldv/common/test.h>
#include "alloc.h"

static int __init ldv_init(void)
{
        __ldv_alloc(4, 14);

	__ldv_alloc(11, 111);

	__ldv_alloc(14, 114);
	__ldv_alloc(15, 115);

	__ldv_alloc(17, 117);

	__ldv_alloc(19, 119);
}

module_init(ldv_init);
