#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/export.h>
#include <linux/workqueue.h>

static struct mutex *mtx;
static int ldv_function(void);
static struct workqueue_struct *myqueue;

static struct delayed_work work1, work2, work3, work4;
static int count;

static void myHandler(struct work_struct *work)
{
	++count;
}

/* Check queue_delayed_work and flush_workqueue */
static int __init ldv_init(void)
{
	myqueue = alloc_workqueue("myqueue", 0, 0);
	if(myqueue == NULL)
		return -ENOMEM;

	INIT_DELAYED_WORK(&work1, myHandler);
	INIT_DELAYED_WORK(&work2, myHandler);
	INIT_DELAYED_WORK(&work3, myHandler);
	INIT_DELAYED_WORK(&work4, myHandler);

	count = 0;

	queue_delayed_work(myqueue, &work1, 10);
	queue_delayed_work(myqueue, &work2, 10);
	queue_delayed_work(myqueue, &work3, 10);
	queue_delayed_work(myqueue, &work4, 10);

	flush_workqueue(myqueue);
	if(count != 4)
	{
		mutex_lock(mtx);
		mutex_lock(mtx);
	}
	return 0;
} 
static void __exit ldv_exit(void)
{
}

module_init(ldv_init);
module_exit(ldv_exit);
