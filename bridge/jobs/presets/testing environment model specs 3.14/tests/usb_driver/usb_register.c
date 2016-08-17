#include <linux/module.h>
#include <linux/usb.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

int flip_a_coin;

int ldv_probe(struct usb_interface *intf, const struct usb_device_id *id)
{
    ldv_invoke_callback();
    return 0;
}

static void ldv_disconnect(struct usb_interface *intf)
{
    ldv_invoke_callback();
}

static struct usb_driver ldv_driver = {
    .name = "ldv-test",
    .probe = ldv_probe,
    .disconnect = ldv_disconnect,
};

static int __init ldv_init(void)
{
    flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        return usb_register(&ldv_driver);
    }
    return 0;
}

static void __exit ldv_exit(void)
{
    if (flip_a_coin) {
        usb_deregister(&ldv_driver);
        ldv_deregister();
    }
}

module_init(ldv_init);
module_exit(ldv_exit);
