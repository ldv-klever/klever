#include <linux/module.h>
#include <scsi/scsi_device.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

int flip_a_coin;

static int ldv_attach(struct scsi_device *sdev)
{
	ldv_invoke_callback();
    return 0;
}

static void ldv_detach(struct scsi_device *sdev)
{
	ldv_invoke_callback();
}

static struct scsi_device_handler ldv_test_struct = {
	.attach = ldv_attach,
	.detach = ldv_detach,
};

static int __init test_init(void)
{
	flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        return scsi_register_device_handler(&ldv_test_struct);
    }
    return 0;
}

static void __exit test_exit(void)
{
	if (flip_a_coin) {
        scsi_unregister_device_handler(&ldv_test_struct);
        ldv_deregister();
    }
}

module_init(test_init);
module_exit(test_exit);
