#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/rtnetlink.h>
#include <net/mac80211.h>

static int __init init(void)
{
	struct ieee80211_hw* hw;
	rtnl_lock();
	ieee80211_unregister_hw(hw);
        rtnl_unlock();
	return 0;
}

module_init(init);
