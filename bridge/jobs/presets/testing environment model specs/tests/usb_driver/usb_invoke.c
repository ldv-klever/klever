#include <linux/module.h>
#include <linux/usb.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

int ldv_probe(struct usb_interface *intf, const struct usb_device_id *id)
{
    ldv_invoke_reached();
}

static void ldv_disconnect(struct usb_interface *intf)
{
    ldv_invoke_reached();
}

static struct usb_driver ldv_driver = {
    .name = "ldv-test",
    .probe = ldv_probe,
    .disconnect = ldv_disconnect
};

static int __init ldv_init(void)
{
    return usb_register(&ldv_driver);
}

static void __exit ldv_exit(void)
{
    usb_deregister(&ldv_driver);
}

module_init(ldv_init);
module_exit(ldv_exit);
