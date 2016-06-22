#include <linux/module.h>
#include <linux/serio.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

static int ldv_connect(struct serio *serio, struct serio_driver *drv)
{
	ldv_invoke_reached();
    return 0;
}

static void ldv_disconnect(struct serio *serio)
{
	ldv_invoke_reached();
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
	return serio_register_driver(&ldv_drv);
}

static void __exit ldv_exit(void)
{
	serio_unregister_driver(&ldv_drv);
}

module_init(ldv_init);
module_exit(ldv_exit);
