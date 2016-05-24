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

static void ldv_close(struct atm_vcc *vcc)
{
	mutex_unlock(ldv_envgen);
}


static int ldv_open(struct atm_vcc *vcc)
{
	int err;
	err = ldv_function();
	if(err){
		return err;
	}
	mutex_lock(ldv_envgen);
	return 0;
}

static struct atmdev_ops ldv_ops = {
	.open		= ldv_open,
	.close		= ldv_close
};

static int __init ldv_init(void)
{
	unsigned long *flags;
	struct atm_dev * dev;
	dev = atm_dev_register("ldv",ldv_parent,&ldv_ops,number,flags);
	if (dev == NULL) {
		return 1;
	}
	return 0;
}

static void __exit ldv_exit(void)
{
	atm_dev_deregister(ldv_dev);
}

module_init(ldv_init);
module_exit(ldv_exit);
