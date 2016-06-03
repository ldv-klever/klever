#include <linux/init.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <linux/vmalloc.h>
#include "md.h"

struct mutex *ldv_envgen;
static int ldv_function(void);
static struct cdev ldv_cdev;
int deg_lock;

struct ldvdriver {
	void (*handler)(void);
};

static int run(struct mddev *mddev)
{
	if(deg_lock){
		mutex_lock(ldv_envgen);
	}
	int err;
	err = ldv_function();
	if (err){
		return err;
	}
	return 0;
}

static int stop(struct mddev *mddev)
{
	if(deg_lock){
		mutex_lock(ldv_envgen);
	}
	return 0;
}

static struct md_personality ldv_personality =
{
	.name		= "ldv",
	.run		= run,
	.stop		= stop,
};

static void handler(void)
{
	unregister_md_personality(&ldv_personality);
	deg_lock = 1;
};

static struct ldvdriver driver = {
	.handler =	handler
};

static int __init ldv_init(void)
{
	deg_lock = 0;
	return register_md_personality(&ldv_personality);
}

static void __exit ldv_exit(void)
{
	//nothing
}

module_init(ldv_init);
module_exit(ldv_exit);
