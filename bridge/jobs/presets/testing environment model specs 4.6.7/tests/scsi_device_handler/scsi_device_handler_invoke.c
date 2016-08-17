#include <linux/module.h>
#include <scsi/scsi_dh.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

static int ldv_attach(struct scsi_device *sdev)
{
	ldv_invoke_reached();
    return 0;
}

static void ldv_detach(struct scsi_device *sdev)
{
	ldv_invoke_reached();
}

static struct scsi_device_handler ldv_test_struct = {
	.attach = ldv_attach,
	.detach = ldv_detach,
};

static int __init test_init(void)
{
	return scsi_register_device_handler(&ldv_test_struct);
}

static void __exit test_exit(void)
{
	scsi_unregister_device_handler(&ldv_test_struct);
}

module_init(test_init);
module_exit(test_exit);
