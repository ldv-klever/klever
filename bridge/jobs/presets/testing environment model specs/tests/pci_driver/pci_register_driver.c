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
int flag;

static struct pci_driver pci_driver;

static void dlock(void) //double lock
{
	mutex_lock(mtx);	
	mutex_lock(mtx);	
}

static int ldv_probe(struct pci_dev *dev, const struct pci_device_id *id)
{
	if(flag)
		dlock();
	return 0;
}
	
static struct pci_driver ldv_driver = {
	.name =		"ldv-test",
	.probe =	ldv_probe,
};

static int __init ldv_init(void)
{
	int ret = ldv_function();
	if(ret)
	{
		int ret_2 =  __pci_register_driver(&ldv_driver, THIS_MODULE, KBUILD_MODNAME);
		if(ret_2)
			flag = 1;
		else
			flag = 0;
	}
	return 0;
}

static void __exit ldv_exit(void)
{
	pci_unregister_driver(&ldv_driver);
}

module_init(ldv_init);
module_exit(ldv_exit);
