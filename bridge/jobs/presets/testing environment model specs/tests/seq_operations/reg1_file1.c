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
int deg_lock;

static void *ldvstart(struct seq_file *file, loff_t *pos)
{
	mutex_lock(ldv_envgen);
	deg_lock++;
}

static void ldvstop(struct seq_file *file, void *iter_ptr)
{
	mutex_lock(ldv_envgen);
	deg_lock--;
}

static const struct seq_operations ldv_ops = {
	.start = ldvstart,
	.stop  = ldvstop,
};

static int __init ldv_init(void)
{
	deg_lock = 0;
	int err;
	err = seq_open(file, &ldv_ops);
	if (err)
		return err;
	return 0;
}

static void __exit ldv_exit(void)
{
	seq_release(inode,file);
}

module_init(ldv_init);
module_exit(ldv_exit);
