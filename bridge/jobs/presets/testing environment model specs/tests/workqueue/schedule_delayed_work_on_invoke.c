#include <linux/module.h>
#include <linux/workqueue.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

static struct delayed_work work;

static void ldv_handler(struct work_struct *work)
{
    ldv_invoke_reached();
}

static int __init ldv_init(void)
{
    int cpu = 1;
    int delay = ldv_undef_int();

	INIT_DELAYED_WORK(&work, ldv_handler);
    schedule_delayed_work_on(cpu, &work, delay);
	return 0;
}

static void __exit ldv_exit(void)
{
    cancel_delayed_work_sync(&work);
}

module_init(ldv_init);
module_exit(ldv_exit);