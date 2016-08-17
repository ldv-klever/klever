#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/irqreturn.h>
#include <linux/iio/triggered_buffer.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

int flip_a_coin;
struct iio_dev * dev;

static irqreturn_t irq_handler(int irq_id, void * data)
{
    ldv_invoke_callback();
	return IRQ_HANDLED;
}

static int __init ldv_init(void)
{
	flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        return iio_triggered_buffer_setup(dev, irq_handler, NULL, NULL);
    }
    return 0;
}

static void __exit ldv_exit(void)
{
	if (flip_a_coin) {
        iio_triggered_buffer_cleanup(dev);
        ldv_deregister();
    }
}

module_init(ldv_init);
module_exit(ldv_exit);

