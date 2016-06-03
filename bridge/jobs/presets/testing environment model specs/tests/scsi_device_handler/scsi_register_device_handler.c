#include <linux/kernel.h>
#include <linux/module.h>
#include <scsi/scsi_dh.h>

struct mutex *ldv_envgen;
static int random_function(void);

static int test_attach(struct scsi_device *sdev)
{
	int ret;
	ret = random_function();
	if(ret == 0){
		mutex_unlock(ldv_envgen);
	}
	return ret;
}

static void test_detach(struct scsi_device *sdev)
{
	mutex_lock(ldv_envgen);
}

static struct scsi_device_handler ldv_test_struct = {
	.name =		"ldv-test",
	.attach =		test_attach,
	.detach =		test_detach,
};

static int __init test_init(void)
{
	int ret;
	ret = scsi_register_device_handler(&ldv_test_struct);
	if(ret == 0){
			mutex_lock(ldv_envgen);
	}
	return ret;
}

static void __exit test_exit(void)
{
	mutex_unlock(ldv_envgen);
	scsi_unregister_device_handler(&ldv_test_struct);
}

module_init(test_init);
module_exit(test_exit);
