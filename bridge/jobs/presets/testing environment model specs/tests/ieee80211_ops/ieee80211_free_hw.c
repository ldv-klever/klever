#include <linux/module.h>
#include <net/mac80211.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

struct mwl8k_priv *priv;

static int ldv_start_callback(struct ieee80211_hw *hw)
{
	ldv_invoke_callback();
    return 0;
}

static void ldv_stop_callback(struct ieee80211_hw *hw)
{
	ldv_invoke_callback();
}

static const struct ieee80211_ops ldv_ops = {
	.start			= ldv_start_callback,
	.stop			= ldv_stop_callback
};

static int __init ldv_init(void)
{
	int flip_a_coin;

	flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        priv = ieee80211_alloc_hw(sizeof(struct ieee80211_ops), &ldv_ops);
        if (priv) {
            ieee80211_free_hw(priv);
            ldv_deregister();
        }
    }
    return 0;
}

static void __exit ldv_exit(void)
{
	/* pass */
}

module_init(ldv_init);
module_exit(ldv_exit);
