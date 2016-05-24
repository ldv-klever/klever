#include <linux/module.h>
#include <linux/wait.h>
#include <linux/atmdev.h>
#include <linux/atm_tcp.h>
#include <linux/bitops.h>
#include <linux/init.h>
#include <linux/slab.h>
#include <asm/uaccess.h>
#include <linux/atomic.h>

struct mutex *ldv_envgen;
static int ldv_function(void);
struct atm_dev *ldv_dev;
struct device *ldv_parent;
int number;
int deg_lock;

struct ldvdriver {
	void (*handler)(void);
};

static void ldv_close(struct atm_vc *vcc)
{
	if(deg_lock){
		mutex_lock(ldv_envgen);
	}
}


static int ldv_open(struct atm_vcc *vcc)
{
	if(deg_lock){
		mutex_lock(ldv_envgen);
	}
	int err;
	err = ldv_function();
	if(err){
		return err;
	}
	return 0;
}

static struct atmdev_ops ldv_ops = {
	.open		= ldv_open,
	.close		= ldv_close
};

static void handler(void)
{
	atm_dev_deregister(ldv_dev);
	deg_lock = 1;
};

static struct ldvdriver driver = {
	.handler =	handler
};

static int __init ldv_init(void)
{
	deg_lock = 0;
	unsigned long *flags;
	int err;
	err = atm_dev_register("ldv",ldv_parent,&ldv_ops,number,flags);
	if (err) {
		return err;
	}
	return 0;
}

static void __exit ldv_exit(void)
{
	//nothing
}

module_init(ldv_init);
module_exit(ldv_exit);
