#include <linux/module.h>
#include <linux/serio.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

int flip_a_coin;

static int ldv_connect(struct serio *serio, struct serio_driver *drv)
{
	ldv_invoke_callback();
    return 0;
}

static void ldv_disconnect(struct serio *serio)
{
	ldv_invoke_callback();
}

static struct serio_driver ldv_drv = {
	.driver		= {
		.name	= "ldv",
	},
	.connect	= ldv_connect,
	.disconnect	= ldv_disconnect,
};

static int __init ldv_init(void)
{
	flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        return serio_register_driver(&ldv_drv);
    }
    return 0;
}

static void __exit ldv_exit(void)
{
	if (flip_a_coin) {
        serio_unregister_driver(&ldv_drv);
        ldv_deregister();
    }
}

module_init(ldv_init);
module_exit(ldv_exit);
