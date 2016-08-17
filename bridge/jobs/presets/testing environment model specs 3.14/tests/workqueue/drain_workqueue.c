#include <linux/module.h>
#include <linux/workqueue.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

static struct workqueue_struct *queue;
static struct work_struct work;

static void ldv_handler(struct work_struct *work)
{
    ldv_invoke_callback();
}

static int __init ldv_init(void)
{
    int flip_a_coin;

	queue = alloc_workqueue("ldv_queue", 0, 0);
	if (!queue)
        return -ENOMEM;

    flip_a_coin = ldv_undef_int();
    ldv_register();
    INIT_WORK(&work, ldv_handler);
    queue_work(queue, &work);

    if (flip_a_coin) {
	    drain_workqueue(queue);
	    ldv_deregister();
	}
	return 0;
}

static void __exit ldv_exit(void)
{
    destroy_workqueue(queue);
}

module_init(ldv_init);
module_exit(ldv_exit);
