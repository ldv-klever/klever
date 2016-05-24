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

//Проверяем schedule_work_on
static int __init ldv_init(void)
{
	count = 0;

	DECLARE_WORK(work1, myHandler);
	DECLARE_WORK(work2, myHandler);
	DECLARE_WORK(work3, myHandler);
	DECLARE_WORK(work4, myHandler);

	schedule_work_on(1, &work1);
	schedule_work_on(1, &work2);
	schedule_work_on(1, &work3);
	schedule_work_on(1, &work4);

	return 0;
}

static void __exit ldv_exit(void)
{
}

module_init(ldv_init);
module_exit(ldv_exit);
