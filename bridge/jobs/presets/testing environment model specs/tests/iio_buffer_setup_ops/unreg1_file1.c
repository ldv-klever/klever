#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/interrupt.h>
#include <linux/irqreturn.h>
#include <linux/iio/iio.h>
#include <linux/iio/buffer.h>
#include <linux/iio/trigger_consumer.h>
#include <linux/iio/triggered_buffer.h>

struct mutex *ldv_envgen;
static int ldv_function(void);
unsigned int irq_id = 100;
struct iio_dev * dev;
int deg_lock = 0;

static int buffer_preenable(struct iio_dev *indio_dev){
	if(deg_lock){
		mutex_lock(ldv_envgen);
	}
	return 0;
}

static const struct iio_buffer_setup_ops buffer_setup_ops = {
          .preenable = &buffer_preenable
};

struct ldvdriver {
	void (*handler)(void);
};

static void handler(void)
{
	iio_triggered_buffer_cleanup(dev);
	deg_lock = 1;
};

static struct ldvdriver driver = {
	.handler =	handler
};

static int __init ldv_init(void)
{
	int err;
	err = iio_triggered_buffer_setup(dev, NULL, NULL, &buffer_setup_ops);
	if (err) {
		return err;
	}
	return 0;
}

static void __exit ldv_exit(void)
{
	//...
}

module_init(ldv_init);
module_exit(ldv_exit);

