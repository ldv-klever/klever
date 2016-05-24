#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/export.h>
#include <linux/workqueue.h>

static struct mutex *mtx;
static int ldv_function(void);
static struct workqueue_struct *myqueue;

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

//Проверяем schedule_delayed_work_on
static int __init ldv_init(void)
{
	count = 0;

	DECLARE_DELAYED_WORK(work1, myHandler);
	DECLARE_DELAYED_WORK(work2, myHandler);
	DECLARE_DELAYED_WORK(work3, myHandler);
	DECLARE_DELAYED_WORK(work4, myHandler);

	schedule_delayed_work_on(1, &work1, 10);
	schedule_delayed_work_on(1, &work2, 10);
	schedule_delayed_work_on(1, &work3, 10);
	schedule_delayed_work_on(1, &work4, 10);
	
	return 0;
}

static void __exit ldv_exit(void)
{
}

module_init(ldv_init);
module_exit(ldv_exit);
