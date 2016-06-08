#include <linux/module.h>
#include <linux/pci.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

int flip_a_coin;
int suspend = 0;

static int ldv_probe(struct pci_dev *dev, const struct pci_device_id *id)
{
    int res;

    ldv_invoke_callback();
    res = ldv_undef_int();
    if (!res)
        ldv_probe_up();
    return res;
}

static void ldv_remove(struct pci_dev *dev)
{
    ldv_release_completely();
    ldv_invoke_callback();
}

static int ldv_suspend(struct pci_dev *dev, pm_message_t state)
{
    ldv_probe_up();
    ldv_invoke_middle_callback();
    return 0;
}

static int ldv_suspend_later(struct pci_dev *dev, pm_message_t state)
{
    ldv_probe_up();
    ldv_invoke_middle_callback();
    return 0;
}

static int ldv_resume_early(struct pci_dev *dev)
{
    ldv_release_down();
    ldv_invoke_middle_callback();
    return 0;
}

static int ldv_resume(struct pci_dev *dev)
{
    ldv_release_down();
    ldv_invoke_middle_callback();
    return 0;
}

static void ldv_shutdown(struct pci_dev *dev)
{
	ldv_invoke_middle_callback();
}

static struct pci_driver ldv_driver = {
	.name =	"ldv-test",
	.probe = ldv_probe,
	.remove = ldv_remove,
	.suspend = ldv_suspend,
	.suspend_late = ldv_suspend_later,
	.resume_early = ldv_resume_early,
	.resume = ldv_resume,
	.shutdown = ldv_shutdown
};

static int __init ldv_init(void)
{
	flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        return pci_register_driver(&ldv_driver);
    }
    return 0;
}

static void __exit ldv_exit(void)
{
	if (flip_a_coin) {
        pci_unregister_driver(&ldv_driver);
        ldv_deregister();
    }
}

module_init(ldv_init);
module_exit(ldv_exit);
