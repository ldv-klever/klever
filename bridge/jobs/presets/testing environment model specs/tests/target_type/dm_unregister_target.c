#include <linux/init.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <linux/vmalloc.h>
#include <linux/device-mapper.h>

struct mutex *ldv_envgen;
static int ldv_function(void);

static int ldvctr(struct dm_target *ti, unsigned int argc, char **argv)
{
	int err;
	err = ldv_function();
	if(err){
		return err;
	}
	mutex_lock(ldv_envgen);
	return 0;
}

static void ldvdtr(struct dm_target *ti)
{
	mutex_unlock(ldv_envgen);
}


static struct target_type ldv_target = {
	.name	     = "ldv",
	.module      = THIS_MODULE,
	.ctr	     = ldvctr,
	.dtr	     = ldvdtr,
};

static int __init ldv_init(void)
{
	int err;
	err = dm_register_target(&ldv_target);
	if (err!=0)
		return err;
	return 0;
}

static void __exit ldv_exit(void)
{
	dm_unregister_target(&ldv_target);
}

module_init(ldv_init);
module_exit(ldv_exit);
