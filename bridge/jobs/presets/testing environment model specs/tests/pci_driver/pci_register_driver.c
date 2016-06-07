#include <linux/module.h>
#include <linux/pci.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

int flip_a_coin;

static int ldv_probe(struct pci_dev *dev, const struct pci_device_id *id)
{
	ldv_invoke_callback();
    return 0;
}

static void ldv_remove(struct pci_dev *dev)
{
	ldv_invoke_callback();
}
	
static struct pci_driver ldv_driver = {
	.name =		"ldv-test",
	.probe =	ldv_probe,
	.remove =	ldv_remove
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
