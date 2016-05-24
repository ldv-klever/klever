#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/export.h>
#include <linux/workqueue.h>

static struct mutex *mtx;
static int ldv_function(void);
static struct workqueue_struct *myqueue;

static struct work_struct work1, work2, work3, work4;

static int count;

static void myHandler(struct work_struct *work)
{
	++count;
	if(count == 4)
	{
		mutex_lock(mtx);
		mutex_lock(mtx);
	}
}

//Проверяем queue_work_on
static int __init ldv_init(void)
{
	myqueue = alloc_workqueue("myqueue", 0, 0);
	
	count = 0;

	INIT_WORK(&work1, myHandler);
	INIT_WORK(&work2, myHandler);
	INIT_WORK(&work3, myHandler);
	INIT_WORK(&work4, myHandler);

	queue_work_on(1, myqueue, &work1);
	queue_work_on(1, myqueue, &work2);
	queue_work_on(1, myqueue, &work3);
	queue_work_on(1, myqueue, &work4);

	return 0;
}

static void __exit ldv_exit(void)
{
}

module_init(ldv_init);
module_exit(ldv_exit);
