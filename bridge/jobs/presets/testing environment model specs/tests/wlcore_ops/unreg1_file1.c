#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/mutex.h>
#include "wlcore.h"

struct mutex *ldv_envgen;
static int ldv_function(void);
int deg_lock;

struct wl1271 *wl;
struct platform_device *pdev;

struct ldvdriver {
	void (*handler)(void);
};

static void handler(void)
{
	wlcore_remove(pdev);
	deg_lock = 1;
};

static struct ldvdriver driver = {
	.handler =	handler
};

static void wl12xx_get_mac(struct wl1271 *wl)
{
	if(deg_lock){
		mutex_lock(ldv_envgen);
	}
}

static struct wlcore_ops wl12xx_ops = {
	.get_mac		= wl12xx_get_mac,
};

static int __init ldv_init(void)
{
	deg_lock = 0;
	int res = wlcore_probe(wl, pdev);
	return res;
}

static void __exit ldv_exit(void)
{
	//wlcore_remove(pdev);
}

module_init(ldv_init);
module_exit(ldv_exit);