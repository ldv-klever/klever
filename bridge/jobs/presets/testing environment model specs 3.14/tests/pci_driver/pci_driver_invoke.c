#include <linux/module.h>
#include <linux/pci.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

static int ldv_probe(struct pci_dev *dev, const struct pci_device_id *id)
{
	ldv_invoke_reached();
    return 0;
}

static void ldv_remove(struct pci_dev *dev)
{
	ldv_invoke_reached();
}

static struct pci_driver ldv_driver = {
	.name =		"ldv-test",
	.probe =	ldv_probe,
	.remove =	ldv_remove
};

static int __init ldv_init(void)
{
    return pci_register_driver(&ldv_driver);
}

static void __exit ldv_exit(void)
{
	pci_unregister_driver(&ldv_driver);
}

module_init(ldv_init);
module_exit(ldv_exit);
