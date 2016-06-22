#include <linux/module.h>
#include <net/mac80211.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

struct mwl8k_priv *priv;

static int ldv_start_callback(struct ieee80211_hw *hw)
{
	ldv_invoke_reached();
	return 0;
}

static void ldv_stop_callback(struct ieee80211_hw *hw)
{
	ldv_invoke_reached();
}

static const struct ieee80211_ops ldv_ops = {
	.start			= ldv_start_callback,
	.stop			= ldv_stop_callback
};

static int __init ldv_init(void)
{
	priv = ieee80211_alloc_hw(sizeof(struct ieee80211_ops), &ldv_ops);
    if (priv) {
        return 0;
    }
    else {
        return -ENOMEM;
    }
}

static void __exit ldv_exit(void)
{
	ieee80211_free_hw(priv);
    ldv_deregister();
}

module_init(ldv_init);
module_exit(ldv_exit);
