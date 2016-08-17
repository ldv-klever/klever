#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

static int ldvprobe(struct platform_device *op)
{
	ldv_invoke_reached();
    return 0;
}

static int ldvremove(struct platform_device *op)
{
	ldv_invoke_reached();
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

static int __init ldv_init(void)
{
	return platform_driver_register(&ldv_platform_driver);
}

static void __exit ldv_exit(void)
{
	platform_driver_unregister(&ldv_platform_driver);
}

module_init(ldv_init);
module_exit(ldv_exit);
