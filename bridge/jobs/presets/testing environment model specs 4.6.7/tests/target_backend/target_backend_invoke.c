#include <linux/module.h>
#include <target/target_core_base.h>
#include <target/target_core_backend.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

struct se_device * ldv_alloc_device(struct se_hba *hba, const char *name)
{
    struct se_device *res;
    ldv_invoke_callback();
    res = ldv_undef_ptr();
    ldv_invoke_reached();
    return res;
}

static void ldv_free_device(struct se_device *device)
{
    ldv_invoke_reached();
}

static struct target_backend_ops ldv_driver = {
    .alloc_device = ldv_alloc_device,
    .free_device = ldv_free_device,
};

static int __init ldv_init(void)
{
    return transport_backend_register(&ldv_driver);
}

static void __exit ldv_exit(void)
{
    target_backend_unregister(&ldv_driver);
}

module_init(ldv_init);
module_exit(ldv_exit);
