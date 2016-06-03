#include <linux/init.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <linux/vmalloc.h>
#include <linux/of_platform.h>
#include <linux/of_device.h>

struct mutex *ldv_envgen;
static int ldv_function(void);
static struct cdev ldv_cdev;
int deg_lock;

struct ldvdriver {
	void (*handler)(void);
};

static int ldvprobe(struct platform_device *op)
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

static int ldvremove(struct platform_device *op)
{
	if(deg_lock){
		mutex_lock(ldv_envgen);
	}
	return 0;
}

static struct platform_driver ldv_platform_driver = {
	.probe = ldvprobe,
	.remove = ldvremove,
	.driver = {
		.name = "ldv",
		.owner = THIS_MODULE,
	},
};

static void handler(void)
{
	platform_driver_unregister(&ldv_platform_driver);
	deg_lock = 1;
};

static struct ldvdriver driver = {
	.handler =	handler
};

static int __init ldv_init(void)
{
	deg_lock = 0;
	return platform_driver_register(&ldv_platform_driver);
}

static void __exit ldv_exit(void)
{
	//nothing
}

module_init(ldv_init);
module_exit(ldv_exit);
