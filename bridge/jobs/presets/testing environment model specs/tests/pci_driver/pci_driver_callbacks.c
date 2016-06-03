#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/pci.h>
#include <linux/slab.h>
#include <linux/module.h>
#include <linux/kernel.h> 
#include <linux/export.h>

static struct mutex *mtx;
static int probing, suspending, l_suspending, resuming, e_resuming, shutdowning;
static int ldv_function(void);

static struct pci_driver pci_driver;

static void lock(int var)
{
	if(var == 1)
	{
		mutex_lock(mtx);	
		mutex_lock(mtx);	
	}
}
	
static void unlock(int var)
{
	if(var == 0)
	{
		mutex_lock(mtx);	
		mutex_lock(mtx);	
	}
}

static int ldv_probe(struct pci_dev *dev, const struct pci_device_id *id)
{
	int ret;
	ret = ldv_function();
	if(ret){
		return ret;
	}

	lock(probing);
	probing = 1;

	unlock(suspending);
	suspending = 0;

	unlock(shutdowning);
	shutdowning = 0;

	return 0;
}

static void ldv_remove(struct pci_dev *dev)
{
	unlock(probing);
	probing = 0;

	if(e_resuming == 0)
	{
		lock(e_resuming);
		e_resuming = 1;
	}

	if(suspending == 0)
	{
		lock(suspending);
		suspending = 1;
	}

	if(l_suspending == 0)
	{
		lock(l_suspending);
		l_suspending = 1;
	}

	if(resuming == 0)
	{
		lock(resuming);
		resuming = 1;
	}

	lock(shutdowning);
	shutdowning = 1;
}

static int ldv_suspend(struct pci_dev *dev, pm_message_t state)
{
	int ret;
	ret = ldv_function();
	if(ret){
		return ret;
	}

	lock(suspending);
	suspending = 1;

	unlock(l_suspending);
	l_suspending = 0;

	unlock(e_resuming);
	e_resuming = 0;

	unlock(resuming);
	resuming = 0;

	return 0;
}

static int ldv_suspend_later(struct pci_dev *dev, pm_message_t state)
{
	int ret;
	ret = ldv_function();
	if(ret){
		return ret;
	}

	lock(l_suspending);
	l_suspending = 1;

	return 0;
}

static int ldv_resume_early(struct pci_dev *dev)
{
	int ret;
	ret = ldv_function();
	if(ret){
		return ret;
	}

	lock(e_resuming);
	e_resuming = 1;

	if(l_suspending == 0)
	{
		lock(l_suspending);
		l_suspending = 1;
	}

	return 0;
}

static int ldv_resume(struct pci_dev *dev)
{
	int ret;
	ret = ldv_function();
	if(ret){
		return ret;
	}

	lock(resuming);
	resuming = 1;

	if(e_resuming==0)
	{
		lock(e_resuming);
		e_resuming = 1;
	}

	if(l_suspending==0)
	{
		lock(l_suspending);
		l_suspending = 1;
	}

	unlock(suspending);
	suspending = 0;

	return 0;
}

static void ldv_shutdown(struct pci_dev *dev)
{
	lock(shutdowning); 	// Like 
	shutdowning = 1;
	unlock(shutdowning); 	// a pro
	shutdowning = 0;

}

static struct pci_driver ldv_driver = {
	.name =		"ldv-test",
	.probe =	ldv_probe,
	.remove =	ldv_remove,
	.suspend = 	ldv_suspend,
	.suspend_late = ldv_suspend_later,
	.resume_early = ldv_resume_early,
	.resume = 	ldv_resume,
	.shutdown = 	ldv_shutdown
};

static int __init ldv_init(void)
{
	int res;
	res = __pci_register_driver(&ldv_driver, THIS_MODULE, KBUILD_MODNAME);
	if(res)
		return res;
	probing = 0;

	resuming = 1;

	e_resuming = 1;

	l_suspending = 1;;

	suspending = 1;

	shutdowning = 1;

	return 0;
}

static void __exit ldv_exit(void)
{
	pci_unregister_driver(&ldv_driver);
}

module_init(ldv_init);
module_exit(ldv_exit);
