#include <linux/init.h>
#include <linux/fs.h>
#include <linux/major.h>
#include <linux/blkdev.h>
#include <linux/module.h>
#include <linux/raw.h>
#include <linux/capability.h>
#include <linux/uio.h>
#include <linux/cdev.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <linux/gfp.h>
#include <linux/compat.h>
#include <linux/vmalloc.h>
#include <asm/uaccess.h>

struct mutex *ldv_envgen;
static int ldv_function(void);
static struct cdev ldv_cdev;
int deg_lock;

static int ldv_open(struct inode *inode, struct file *filp)
{
	int err;
	err = ldv_function();
	if (err){
		return err;
	}
	mutex_lock(ldv_envgen);
	deg_lock++;
	return 0;
}

static int ldv_release(struct inode *inode, struct file *filp)
{
	mutex_lock(ldv_envgen);
	deg_lock--;
	return 0;
}

static const struct file_operations ldv_fops = {
	.open		= ldv_open,
	.release	= ldv_release,
	.owner		= THIS_MODULE,
};

static int __init ldv_init(void)
{
	deg_lock = 0;
	int err = ldv_function();
	if (err){
		return err;
	}
	cdev_init(&ldv_cdev, &ldv_fops);
	return 0;
}

static void __exit ldv_exit(void)
{
	cdev_del(&ldv_cdev);
	if(deg_lock==1){
		mutex_unlock(ldv_envgen);
	}
}

module_init(ldv_init);
module_exit(ldv_exit);
