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

static void deg_close(struct atm_dev *dev)
{
	mutex_lock(ldv_envgen);
	deg_lock--;
}


static int deg_open(struct atm_vcc *vcc)
{
	int err = ldv_function();
	if(err){
		return err;
	}
	mutex_lock(ldv_envgen);
	deg_lock++;
	return 0;
}

static struct atmdev_ops ldv_ops = {
	.open		= deg_open,
	.close		= deg_close
};

static int __init ldv_init(void)
{
	deg_lock = 0;
	unsigned long *flags;
	int err;
	err = ldv_function();
	if (err) {
		return err;
	}
	atm_dev_register("ldv", ldv_parent, &ldv_ops, number, flags);
	return 0;
}

static void __exit ldv_exit(void)
{
	atm_dev_deregister(ldv_dev);
	if(deg_lock == 1){
		mutex_unlock(ldv_envgen);
	}
}

module_init(ldv_init);
module_exit(ldv_exit);
