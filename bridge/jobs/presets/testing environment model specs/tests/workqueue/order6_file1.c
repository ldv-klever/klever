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
}

//Проверяем flush_scheduled_work
static int __init ldv_init(void)
{
	count = 0;

	INIT_WORK(&work1, myHandler);
	INIT_WORK(&work2, myHandler);
	INIT_WORK(&work3, myHandler);
	INIT_WORK(&work4, myHandler);

	schedule_work(&work1);
	schedule_work(&work2);
	schedule_work(&work3);
	schedule_work(&work4);
	
	flush_scheduled_work();
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
