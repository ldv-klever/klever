#include <linux/module.h>
#include <linux/interrupt.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

static void ldv_handler(unsigned long);
DECLARE_TASKLET_DISABLED(tasklet, ldv_handler, 0);

static void ldv_handler(unsigned long data)
{
	ldv_invoke_reached();
}

static int __init ldv_init(void)
{
	ldv_invoke_test();
	tasklet_schedule(&tasklet);
	return 0;
}

static void __exit ldv_exit(void)
{
	tasklet_kill(&tasklet);
}

module_init(ldv_init);
module_exit(ldv_exit);
