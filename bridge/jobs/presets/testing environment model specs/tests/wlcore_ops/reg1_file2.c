#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/mutex.h>
#include "wlcore.h"

struct mutex *ldv_envgen;
static int ldv_function(void);

struct wl1271 *wl;
struct platform_device *pdev;

static void wl12xx_get_mac(struct wl1271 *wl)
{
	mutex_lock(ldv_envgen);
	mutex_lock(ldv_envgen);
}

static struct wlcore_ops wl12xx_ops = {
	.get_mac		= wl12xx_get_mac,
};

static int __init ldv_init(void)
{
	int res = wlcore_probe(wl, pdev);
	return res;
}

static void __exit ldv_exit(void)
{
	wlcore_remove(pdev);
}

module_init(ldv_init);
module_exit(ldv_exit);