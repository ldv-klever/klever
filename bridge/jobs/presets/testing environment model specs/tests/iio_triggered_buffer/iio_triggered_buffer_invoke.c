#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/irqreturn.h>
#include <linux/iio/triggered_buffer.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

struct iio_dev * dev;

static irqreturn_t irq_handler(int irq_id, void * data)
{
    ldv_invoke_reached();
	return IRQ_HANDLED;
}

static int __init ldv_init(void)
{
	return iio_triggered_buffer_setup(dev, irq_handler, NULL, NULL);
}

static void __exit ldv_exit(void)
{
	iio_triggered_buffer_cleanup(dev);
}

module_init(ldv_init);
module_exit(ldv_exit);

