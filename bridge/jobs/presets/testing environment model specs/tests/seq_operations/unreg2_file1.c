#include <linux/init.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <linux/vmalloc.h>
#include <linux/err.h>
#include <linux/seq_file.h>

struct mutex *ldv_envgen;
static int ldv_function(void);
struct file *file;
struct inode * inode;
int psize;

int deg_lock;
struct ldvdriver {
	void (*handler)(void);
};

static void *ldvstart(struct seq_file *file, loff_t *pos)
{
	if(deg_lock){
		mutex_lock(ldv_envgen);
	}
}

static void ldvstop(struct seq_file *file, void *iter_ptr)
{
	if(deg_lock){
		mutex_lock(ldv_envgen);
	}
}

static const struct seq_operations ldv_ops = {
	.start = ldvstart,
	.stop  = ldvstop,
};

static void handler(void)
{
	seq_release_private(inode,file);
	deg_lock = 1;
};

static struct ldvdriver driver = {
	.handler =	handler
};

static int __init ldv_init(void)
{
	deg_lock = 0;
	int err;
	err = seq_open_private(file, &ldv_ops, psize);
	if (!err)
		return err;
	return 0;
}

static void __exit ldv_exit(void)
{
	//nothing
}

module_init(ldv_init);
module_exit(ldv_exit);
