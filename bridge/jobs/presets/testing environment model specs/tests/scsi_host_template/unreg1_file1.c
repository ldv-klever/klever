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
int deg_lock;


struct ldvdriver {
	void (*handler)(void);
};

static int ldvreset(struct scsi_cmnd *cmd){
	if(deg_lock){
		mutex_lock(ldv_envgen);
	}
}

static struct scsi_host_template ldv_template = {
	.eh_bus_reset_handler   = ldvreset,
};

static void handler(void)
{
	scsi_remove_host(instance);
	deg_lock = 1;
};

static struct ldvdriver driver = {
	.handler =	handler
};

static int __init ldv_init(void)
{
	deg_lock = 0;
	int err;
	err = scsi_host_alloc( &ldv_template, privsize);
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
