#include <linux/init.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <linux/vmalloc.h>
#include <linux/serio.h>

struct mutex *ldv_envgen;
static int ldv_function(void);
int deg_lock;

struct ldvdriver {
	void (*handler)(void);
};

static void ldvdisconnect(struct serio *serio)
{
	if(deg_lock){
		mutex_lock(ldv_envgen);
	}
}

static int ldvconnect(struct serio *serio, struct serio_driver *drv)
{
	if(deg_lock){
		mutex_lock(ldv_envgen);
	}
	int err;
	err = ldv_function();
	if(err){
		return err;
	}
	return 0;
}


static struct serio_driver ldv_drv = {
	.driver		= {
		.name	= "ldv",
	},
	.connect	= ldvconnect,
	.disconnect	= ldvdisconnect,
};

static void handler(void)
{
	serio_unregister_driver(&ldv_drv);
	deg_lock = 1;
};

static struct ldvdriver driver = {
	.handler =	handler
};

static int __init ldv_init(void)
{
	deg_lock = 0;
	int err;
	err = __serio_register_driver(&ldv_drv,THIS_MODULE,"modname");
	if (err)
		return err;
	return 0;
}

static void __exit ldv_exit(void)
{
	//nothing
}

module_init(ldv_init);
module_exit(ldv_exit);
