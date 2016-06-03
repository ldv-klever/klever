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

static irqreturn_t irq_handler1(int irq_id, void * data){
	if(deg_lock){
		mutex_lock(ldv_envgen);
	}
	return IRQ_HANDLED;
}

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
	err = iio_triggered_buffer_setup(dev, irq_handler1, NULL, NULL);
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

