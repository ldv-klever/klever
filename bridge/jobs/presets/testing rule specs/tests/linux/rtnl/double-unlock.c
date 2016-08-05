#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/rtnetlink.h>

static int __init init(void)
{
	rtnl_unlock();
        return 0;
}

module_init(init);
