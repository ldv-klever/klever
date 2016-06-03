#include <linux/init.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <linux/vmalloc.h>
#include "md.h"

struct mutex *ldv_envgen;
static int ldv_function(void);
static struct cdev ldv_cdev;

static int run(struct mddev *mddev)
{
	int err;
	err = ldv_function();
	if (err){
		return err;
	}
	mutex_lock(ldv_envgen);
	return 0;
}

static int stop(struct mddev *mddev)
{
	mutex_unlock(ldv_envgen);
	return 0;
}

static struct md_personality ldv_personality =
{
	.name		= "ldv",
	.run		= run,
	.stop		= stop,
};

static int __init ldv_init(void)
{
	return register_md_personality(&ldv_personality);
}

static void __exit ldv_exit(void)
{
	unregister_md_personality(&ldv_personality);
}

module_init(ldv_init);
module_exit(ldv_exit);
