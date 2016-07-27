#include <linux/module.h>
#include <linux/tty.h>
#include <linux/usb.h>
#include <linux/usb/serial.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

int flip_a_coin;
const struct usb_device_id *id_table;

int ldv_probe(struct usb_serial *serial, const struct usb_device_id *id)
{
    int res;

    ldv_invoke_callback();
    res = ldv_undef_int();
    if (!res)
        ldv_probe_up();
    return res;
}

void ldv_release(struct usb_serial *serial)
{
    ldv_release_down();
    ldv_invoke_callback();
}

static struct usb_serial_driver ldv_driver = {
    .probe = ldv_probe,
    .release = ldv_release,
};

static struct usb_serial_driver * const ldv_drivers[] = {
         &ldv_driver, NULL
};

static int __init ldv_init(void)
{
    flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        return usb_serial_register_drivers(ldv_drivers, "ldv_driver", id_table);
    }
    return 0;
}

static void __exit ldv_exit(void)
{
    if (flip_a_coin) {
        usb_serial_deregister_drivers(ldv_drivers);
        ldv_deregister();
    }
}

module_init(ldv_init);
module_exit(ldv_exit);
