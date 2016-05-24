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

struct mutex *ldv_envgen;
static int ldv_function(void);
unsigned int major;
int deg_lock;

struct ldvdriver {
	void (*handler)(void);
};
 
static int ldv_open(struct inode *inode, struct file *filp)
{
	if(deg_lock){
		mutex_lock(ldv_envgen);
	}
	int err;
	err = ldv_function();
	if (err){
		return err;
	}
	return 0;
}

static int ldv_release(struct inode *inode, struct file *filp)
{
	if(deg_lock){
		mutex_lock(ldv_envgen);
	}
	return 0;
}

static const struct file_operations ldv_fops = {
	.open		= ldv_open,
	.release	= ldv_release,
	.llseek		= default_llseek,
	.owner		= THIS_MODULE,
};

static void handler(void)
{
	unregister_chrdev(major, "ldv");
	deg_lock = 1;
};

static struct ldvdriver driver = {
	.handler =	handler
};

static int __init ldv_init(void)
{
	deg_lock = 0;
	if (register_chrdev(major, "ldv", &ldv_fops)) {
		return -ENODEV;
	}
	return 0;
}

static void __exit ldv_exit(void)
{
	//nothing
}

module_init(ldv_init);
module_exit(ldv_exit);
