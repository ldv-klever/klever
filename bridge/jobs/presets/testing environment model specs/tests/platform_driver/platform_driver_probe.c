#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

int flip_a_coin;

static int ldvprobe(struct platform_device *op)
{
	ldv_invoke_callback();
    return 0;
}

static int ldvremove(struct platform_device *op)
{
	ldv_invoke_callback();
    return 0;
}

static struct platform_driver ldv_platform_driver = {
	.remove = ldvremove,
	.driver = {
		.name = "ldv",
		.owner = THIS_MODULE,
	},
};

static int __init ldv_init(void)
{
	flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        return platform_driver_probe(&ldv_platform_driver, &ldvprobe);
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