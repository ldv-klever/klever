#include <linux/module.h>
#include <linux/tty.h>
#include <linux/usb.h>
#include <linux/usb/serial.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

const struct usb_device_id *id_table;

int ldv_probe(struct usb_serial *serial, const struct usb_device_id *id)
{
    ldv_invoke_callback();
    return 0;
}

void ldv_release(struct usb_serial *serial)
{
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
    int flip_a_coin;

    flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        if (!usb_serial_register_drivers(ldv_drivers, "ldv_driver", id_table)) {
             usb_serial_deregister_drivers(ldv_drivers);
            ldv_deregister();
        }
    }
    return 0;
}

static void __exit ldv_exit(void)
{
    /* pass */
}

module_init(ldv_init);
module_exit(ldv_exit);
