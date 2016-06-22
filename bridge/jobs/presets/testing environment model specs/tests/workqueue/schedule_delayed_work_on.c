#include <linux/module.h>
#include <linux/workqueue.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

int flip_a_coin;
static struct delayed_work work;

static void ldv_handler(struct work_struct *work)
{
    ldv_invoke_callback();
}

static int __init ldv_init(void)
{
    int cpu = 1;
    int delay = ldv_undef_int();

	flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
	    INIT_DELAYED_WORK(&work, ldv_handler);
        ldv_register();
	    schedule_delayed_work_on(cpu, &work, delay);
	}
	return 0;
}

static void __exit ldv_exit(void)
{
    if (flip_a_coin) {
        cancel_delayed_work_sync(&work);
        ldv_deregister();
    }
}

module_init(ldv_init);
module_exit(ldv_exit);