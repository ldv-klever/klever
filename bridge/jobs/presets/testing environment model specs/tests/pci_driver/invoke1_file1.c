#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/pci.h>
#include <linux/slab.h>
#include <linux/module.h>
#include <linux/kernel.h> 
#include <linux/export.h>

static struct mutex *mtx;
static int ldv_function(void);

static struct pci_driver pci_driver;

static void dlock(void) //double lock
{
	mutex_lock(mtx);	
	mutex_lock(mtx);	
}
	
static int ldv_probe(struct pci_dev *dev, const struct pci_device_id *id)
{
	dlock();
	return 0;
}

static void ldv_remove(struct pci_dev *dev)
{
	dlock();
}

static int ldv_suspend(struct pci_dev *dev, pm_message_t state)
{
	dlock();
	return 0;
}

static int ldv_suspend_later(struct pci_dev *dev, pm_message_t state)
{
	dlock();
	return 0;
}

static int ldv_resume_early(struct pci_dev *dev)
{
	dlock();
	return 0;
}

static int ldv_resume(struct pci_dev *dev)
{
	dlock();
	return 0;
}

static void ldv_shutdown(struct pci_dev *dev)
{
	dlock();
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
	return 0;
}

static void __exit ldv_exit(void)
{
	pci_unregister_driver(&ldv_driver);
}

module_init(ldv_init);
module_exit(ldv_exit);
