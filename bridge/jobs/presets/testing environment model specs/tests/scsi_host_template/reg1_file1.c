#include <linux/init.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <linux/vmalloc.h>
#include "scsi.h"

struct mutex *ldv_envgen;
static int ldv_function(void);
struct rtc_device *rtc;
struct Scsi_Host *instance;
int privsize;

static int ldvreset(struct scsi_cmnd *cmd){
	mutex_lock(ldv_envgen);
}

static struct scsi_host_template ldv_template = {
	.eh_bus_reset_handler   = ldvreset,
};

static int __init ldv_init(void)
{
	int err;
	err = scsi_host_alloc( &ldv_template, privsize);
	if (!err)
		return err;
	return 0;
}

static void __exit ldv_exit(void)
{
	scsi_unregister(instance);
}

module_init(ldv_init);
module_exit(ldv_exit);
