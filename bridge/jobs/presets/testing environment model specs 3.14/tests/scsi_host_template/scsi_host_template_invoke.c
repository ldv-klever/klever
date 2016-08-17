#include <linux/module.h>
#include <linux/device.h>
#include <scsi/scsi_host.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

struct device *dev;
struct Scsi_Host host;

static int ldv_reset(struct scsi_cmnd *cmd){
	ldv_invoke_reached();
    return 0;
}

static struct scsi_host_template ldv_template = {
	.eh_bus_reset_handler   = ldv_reset,
};

static int __init ldv_init(void)
{
	host.hostt = & ldv_template;
    return scsi_add_host(& host, dev);
}

static void __exit ldv_exit(void)
{
	scsi_unregister(& host);
}

module_init(ldv_init);
module_exit(ldv_exit);
