#include <linux/module.h>
#include <linux/workqueue.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

static struct workqueue_struct *queue;
static struct delayed_work work;

static void ldv_handler(struct work_struct *work)
{
    ldv_invoke_reached();
}

static int __init ldv_init(void)
{
    int cpu = 1;
    int delay = ldv_undef_int();

	queue = alloc_workqueue("ldv_queue", 0, 0);
	if (!queue)
        return -ENOMEM;

    INIT_DELAYED_WORK(&work, ldv_handler);
    queue_delayed_work_on(cpu, queue, &work, delay);
	return 0;
}

static void __exit ldv_exit(void)
{
    cancel_delayed_work(&work);
    destroy_workqueue(queue);
}

module_init(ldv_init);
module_exit(ldv_exit);
