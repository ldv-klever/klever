#include <linux/bio.h>
#include <linux/slab.h>
#include <linux/dm-dirty-log.h>
#include <linux/device-mapper.h>
#include <linux/dm-log-userspace.h>
#include <linux/module.h>
#include <asm/uaccess.h>

struct mutex *ldv_envgen;
struct mutex *ldv_envgen2;
static int ldv_function(void);
static struct cdev ldv_cdev;
int deg_lock;
 
static int ldv_ctr(struct dm_dirty_log *log, struct dm_target *ti, unsigned argc, char **argv)
{
	int err = ldv_function();
	if (err){
		return err;
	}
	mutex_lock(ldv_envgen);
	deg_lock++;
	return 0;
}

static void ldv_dtr(struct dm_dirty_log *log)
{
	mutex_lock(ldv_envgen);
	deg_lock--;
	return 0;
}

static void ldv_mark_region(struct dm_dirty_log *log, region_t region);

static void ldv_clear_region(struct dm_dirty_log *log, region_t region);

static struct dm_dirty_log_type ldv_type = {
	.name = "ldv",
	.module = THIS_MODULE,
	.ctr = ldv_ctr,
	.dtr = ldv_dtr,
	.mark_region = ldv_mark_region,
	.clear_region = ldv_clear_region,
};

static int __init ldv_init(void)
{
	deg_lock = 0;
	int err;
	err = dm_dirty_log_type_register(&ldv_type);
	if (err){
		return err;
	}
	return 0;
}

static void __exit ldv_exit(void)
{
	dm_dirty_log_type_unregister(&ldv_type);
	if(deg_lock==1){
		mutex_unlock(ldv_envgen);
	}
}

module_init(ldv_init);
module_exit(ldv_exit);
