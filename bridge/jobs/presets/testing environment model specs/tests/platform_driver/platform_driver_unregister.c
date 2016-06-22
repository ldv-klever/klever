#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

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
	.probe = ldvprobe,
	.remove = ldvremove,
	.driver = {
		.name = "ldv",
		.owner = THIS_MODULE,
	},
};

static int __init ldv_init(void)
{
	int flip_a_coin;

	flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        if (!platform_driver_register(&ldv_platform_driver)) {
            platform_driver_unregister(&ldv_platform_driver);
            ldv_deregister();
        }
    }
    return 0;
}

static void __exit ldv_exit(void)
{
	/* pass */
}

module_init(ldv_init);
module_exit(ldv_exit);
