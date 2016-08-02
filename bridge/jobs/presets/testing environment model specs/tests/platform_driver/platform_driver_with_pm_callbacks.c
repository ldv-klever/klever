#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/pm.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

int flip_a_coin;

static int ldvprobe(struct platform_device *op)
{
    int res;

    ldv_invoke_callback();
    res = ldv_undef_int();
    if (!res)
        ldv_probe_up();
    return res;
}

static int ldvremove(struct platform_device *op)
{
	ldv_release_completely();
    ldv_invoke_callback();
    return 0;
}

static int test_suspend(struct device *dev)
{
	ldv_probe_up();
    ldv_invoke_middle_callback();
    return 0;
}

static int test_resume(struct device *dev)
{
	ldv_release_down();
    ldv_invoke_middle_callback();
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
	flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        return platform_driver_register(&ldv_platform_driver);
    }
    return 0;
}

static void __exit ldv_exit(void)
{
	if (flip_a_coin) {
        platform_driver_unregister(&ldv_platform_driver);
        ldv_deregister();
    }
}

module_init(ldv_init);
module_exit(ldv_exit);

