#include <linux/module.h>
#include <linux/init.h>
#include <linux/mutex.h>
#include "hwbus.h"

struct mutex *ldv_envgen;
static int ldv_function(void);

static void ldv_lock(struct hwbus_priv *self){
	mutex_lock(ldv_envgen);
}

static void ldv_unlock(struct hwbus_priv *self){
	mutex_unlock(ldv_envgen);
}

static struct hwbus_ops ldv_hwbus_ops = {
        .lock                   = ldv_lock,
        .unlock                 = ldv_unlock,
};

static int __init ldv_init(void)
{
	int err;
	/* insert proper registration here */
	err = ldv_function();
	if (err) {
		return err;
	}
	return 0;
}

static void __exit ldv_exit(void)
{
	/* insert proper deregistration here */
	return;
}

module_init(ldv_init);
module_exit(ldv_exit);
