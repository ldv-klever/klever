#include <linux/init.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <linux/vmalloc.h>
#include <linux/serio.h>

struct mutex *ldv_envgen;
static int ldv_function(void);

static void ldvdisconnect(struct serio *serio)
{
	mutex_unlock(ldv_envgen);
}

static int ldvconnect(struct serio *serio, struct serio_driver *drv)
{
	int err;
	err = ldv_function();
	if(err){
		return err;
	}
	mutex_lock(ldv_envgen);
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
	int err;
	err = __serio_register_driver(&ldv_drv,THIS_MODULE,"modname");
	if (err)
		return err;
	return 0;
}

static void __exit ldv_exit(void)
{
	serio_unregister_driver(&ldv_drv);
}

module_init(ldv_init);
module_exit(ldv_exit);
