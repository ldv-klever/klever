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

static int ldvprobe(struct platform_device *op)
{
	int err = ldv_function();
	if(err){
		return err;
	}
	mutex_lock(ldv_envgen);
	deg_lock++;
	return 0;
}

static int ldvremove(struct platform_device *op)
{
	mutex_lock(ldv_envgen);
	deg_lock--;
}

static struct platform_driver ldv_platform_driver = {
	.probe = ldvprobe,
	.remove = ldvremove,
	.driver = {
		.name = "ldv",
		.owner = THIS_MODULE,
	},
};

static int __init ldv_init(void)
{
	deg_lock = 0;
	int err;
	err = platform_driver_register(&ldv_platform_driver);
	if (err) {
		return err;
	}
	return 0;
}

static void __exit ldv_exit(void)
{
	platform_driver_unregister(&ldv_platform_driver);
	if(deg_lock==1){
		mutex_unlock(ldv_envgen);
	}
}

module_init(ldv_init);
module_exit(ldv_exit);
