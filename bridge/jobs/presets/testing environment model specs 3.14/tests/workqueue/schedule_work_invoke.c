#include <linux/module.h>
#include <linux/workqueue.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

static struct work_struct work;

static void ldv_handler(struct work_struct *work)
{
    ldv_invoke_reached();
}

static int __init ldv_init(void)
{
	INIT_WORK(&work, ldv_handler);
    schedule_work(&work);
	return 0;
}

static void __exit ldv_exit(void)
{
    cancel_work_sync(&work);
}

module_init(ldv_init);
module_exit(ldv_exit);

