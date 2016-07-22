#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/rtnetlink.h>

static int __init init(void)
{
	if (rtnl_trylock()) rtnl_unlock();
	
	rtnl_lock();
	if (rtnl_is_locked()) rtnl_unlock();
	
	rtnl_lock();
	rtnl_unlock();
        return 0;
}

module_init(init);
