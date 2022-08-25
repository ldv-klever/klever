#include <linux/module.h>
#include <linux/kthread.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

void *data;
static struct task_struct *thread;

static int ldv_handler(void *data)
{
	ldv_invoke_reached();
	ldv_check_resource1(data, 0);
	return 0;
}

static int __init ldv_init(void)
{
	data = ldv_undef_ptr_non_null();
	ldv_invoke_test();
	ldv_store_resource1(data);
	thread = kthread_run(ldv_handler, data, "kthread_handler");
	return 0;
}

static void __exit ldv_exit(void)
{
	kthread_stop(thread);
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");