#include <linux/module.h>
#include <linux/workqueue.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

static struct workqueue_struct *queue;
static struct work_struct work;

static void ldv_handler(struct work_struct *work)
{
    ldv_invoke_reached();
}

static int __init ldv_init(void)
{
    int cpu = 1;

	queue = alloc_workqueue("ldv_queue", 0, 0);
	if (!queue)
        return -ENOMEM;

    INIT_WORK(&work, ldv_handler);
    queue_work_on(cpu, queue, &work);
	return 0;
}

static void __exit ldv_exit(void)
{
    cancel_work_sync(&work);
    destroy_workqueue(queue);
}

module_init(ldv_init);
module_exit(ldv_exit);
