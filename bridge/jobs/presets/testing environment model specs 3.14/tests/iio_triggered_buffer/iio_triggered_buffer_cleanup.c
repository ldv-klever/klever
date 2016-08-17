#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/irqreturn.h>
#include <linux/iio/triggered_buffer.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

struct iio_dev * dev;

static irqreturn_t irq_handler(int irq_id, void * data)
{
    ldv_invoke_callback();
	return IRQ_HANDLED;
}

static int __init ldv_init(void)
{
	int flip_a_coin;

    flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        if (!iio_triggered_buffer_setup(dev, irq_handler, NULL, NULL)) {
            iio_triggered_buffer_cleanup(dev);
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

