#include <linux/module.h>
#include <linux/device.h>
#include <scsi/scsi_host.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

int flip_a_coin;
struct device *dev;
struct Scsi_Host *host;

static int ldv_reset(struct scsi_cmnd *cmd){
	ldv_invoke_callback();
    return 0;
}

static struct scsi_host_template ldv_template = {
	.eh_bus_reset_handler   = ldv_reset,
};

static int __init ldv_init(void)
{
	flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        host = scsi_host_alloc(&ldv_template, sizeof(void *));
        if (host) {
            ldv_register();
	        return scsi_add_host(host, dev);
        }
        else
            return -ENOMEM;
    }
    return 0;
}

static void __exit ldv_exit(void)
{
	if (flip_a_coin) {
        scsi_unregister(host);
        ldv_deregister();
    }
}

module_init(ldv_init);
module_exit(ldv_exit);
