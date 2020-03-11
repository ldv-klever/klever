#include <linux/module.h>
#include <linux/interrupt.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

unsigned long data;
static struct tasklet_struct t;

static void ldv_handler(unsigned long data)
{
	ldv_invoke_reached();
}

static int __init ldv_init(void)
{
	ldv_invoke_test();
	data = ldv_undef_ulong();
	tasklet_init(&t, ldv_handler, data);
	tasklet_hi_schedule_first(&t);
	return 0;
}

static void __exit ldv_exit(void)
{
	tasklet_kill(&t);
}

module_init(ldv_init);
module_exit(ldv_exit);