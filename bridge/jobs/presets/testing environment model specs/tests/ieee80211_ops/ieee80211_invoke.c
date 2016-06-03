#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/mutex.h>
#include <net/mac80211.h>

struct mutex *ldv_envgen;
struct mwl8k_priv *priv;
static int ldv_function(void);
int deg_lock;

static int ldv_start_callback(struct ieee80211_hw *hw)
{
	int err;
	err = ldv_function();
	if(err){
		return err;
	}
	mutex_lock(ldv_envgen);
	deg_lock++;
	return err;
}

static void ldv_stop_callback(struct ieee80211_hw *hw)
{
	mutex_lock(ldv_envgen);
	deg_lock--;
}

static const struct ieee80211_ops ldv_ops = {
	.start			= ldv_start_callback,
	.stop			= ldv_stop_callback
};

static int __init ldv_init(void)
{
	deg_lock = 0;
	priv = ieee80211_alloc_hw(sizeof(struct ieee80211_ops), &ldv_ops);
	if (!priv) {
		return -ENOMEM;
	}
	return 0;
}

static void __exit ldv_exit(void)
{
	ieee80211_free_hw(priv);
	if(deg_lock==1){
		mutex_unlock(ldv_envgen);
	}
}

module_init(ldv_init);
module_exit(ldv_exit);
