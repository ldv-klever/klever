#include <linux/module.h>
#include <target/target_core_base.h>
#include <target/target_core_backend.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

int flip_a_coin;

struct se_device * ldv_alloc_device(struct se_hba *hba, const char *name)
{
    struct se_device *res;

    ldv_invoke_callback();
    res = ldv_undef_ptr();
    if (res)
        ldv_probe_up();
    return res;
}

static void ldv_free_device(struct se_device *device)
{
    ldv_release_down();
    ldv_invoke_callback();
}

static struct se_subsystem_api ldv_driver = {
    .alloc_device = ldv_alloc_device,
    .free_device = ldv_free_device,
};

static int __init ldv_init(void)
{
    flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        return transport_subsystem_register(&ldv_driver);
    }
    return 0;
}

static void __exit ldv_exit(void)
{
    if (flip_a_coin) {
        transport_subsystem_release(&ldv_driver);
        ldv_deregister();
    }
}

module_init(ldv_init);
module_exit(ldv_exit);
