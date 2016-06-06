#include <linux/init.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <linux/vmalloc.h>
#include <linux/serio.h>

struct mutex *ldv_envgen;
static int ldv_function(void);
int deg_lock;

static void ldvdisconnect(struct serio *serio)
{
	mutex_lock(ldv_envgen);
	deg_lock--;
}

static int ldvconnect(struct serio *serio, struct serio_driver *drv)
{
	int err = ldv_function();
	if(err){
		return err;
	}
	mutex_lock(ldv_envgen);
	deg_lock++;
	return 0;
}


static struct serio_driver ldv_drv = {
	.driver		= {
		.name	= "ldv",
	},
	.connect	= ldvconnect,
	.disconnect	= ldvdisconnect,
};

static int __init ldv_init(void)
{
	deg_lock = 0;
	int err;
	err = serio_register_driver(&ldv_drv);
	if (err)
		return err;
	return 0;
}

static void __exit ldv_exit(void)
{
	serio_unregister_driver(&ldv_drv);
	if(deg_lock==1){
		mutex_unlock(ldv_envgen);
	}
}

module_init(ldv_init);
module_exit(ldv_exit);
