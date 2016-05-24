#include <linux/init.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <linux/vmalloc.h>
#include <linux/of_platform.h>
#include <linux/pm.h>
#include <linux/of_device.h>

struct mutex *ldv_envgen;
static int ldv_function(void);
static struct cdev ldv_cdev;

static int ldvprobe(struct platform_device *op)
{
	int err;
	err = ldv_function();
	if(err){
		return err;
	}
	mutex_lock(ldv_envgen);
	return 0;
}

static int ldvremove(struct platform_device *op)
{
	mutex_unlock(ldv_envgen);
}

static int test_suspend(struct device *dev)
{
	mutex_lock(ldv_envgen);
	return 0;
}

static int test_resume(struct device *dev)
{
	mutex_lock(ldv_envgen);
	return 0;
}


static SIMPLE_DEV_PM_OPS(test_pm_ops, test_suspend, test_resume);

static struct platform_driver ldv_platform_driver = {
	.probe = ldvprobe,
	.remove = ldvremove,
	.driver = {
		.name = "ldv",
		.owner = THIS_MODULE,
		.pm = &test_pm_ops
	},
};

static int __init ldv_init(void)
{
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
}

module_init(ldv_init);
module_exit(ldv_exit);
