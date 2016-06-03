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

struct ldvdriver
{
	void (*handler)(void);
};

static struct pci_driver pci_driver;

static int ldv_probe(struct pci_dev *dev, const struct pci_device_id *id)
{
	if(flag)
	{
		mutex_lock(mtx);
	}
	int ret;
	ret = ldv_function();
	if(ret){
		return ret;
	}
	return 0;
}

static void ldv_remove(struct pci_dev *dev)
{
	if(flag)
	{
		mutex_lock(mtx);
	}
}
	
static struct pci_driver ldv_driver = {
	.name =		"ldv-test",
	.probe =	ldv_probe,
	.remove = 	ldv_remove
};

static void handler(void)
{
	pci_unregister_driver(&ldv_driver);
	flag = 1;
}

static struct ldvdriver driver = 
{
	.handler = handler
};

static int __init ldv_init(void)
{
	flag = 0;
	int ret;
	ret =  __pci_register_driver(&ldv_driver, THIS_MODULE, KBUILD_MODNAME);
	return ret;
}

static void __exit ldv_exit(void)
{
	//nothing especially
}

module_init(ldv_init);
module_exit(ldv_exit);
