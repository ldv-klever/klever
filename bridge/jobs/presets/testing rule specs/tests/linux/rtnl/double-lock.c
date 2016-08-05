#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/rtnetlink.h>

static int __init init(void)
{
	rtnl_lock();
        rtnl_lock();
	return 0;
}

module_init(init);
