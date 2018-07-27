#include <linux/module.h>
#include <linux/kthread.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

void *data;
static struct task_struct *thread;

static int ldv_handler(void *data)
{
	ldv_invoke_reached();
}

static int __init ldv_init(void)
{
	data = ldv_undef_ptr();
	ldv_invoke_test();
	thread = kthread_run(ldv_handler, data, "kthread_handler");
	return 0;
}

static void __exit ldv_exit(void) 
{
	kthread_stop(thread);
}

module_init(ldv_init);
module_exit(ldv_exit);