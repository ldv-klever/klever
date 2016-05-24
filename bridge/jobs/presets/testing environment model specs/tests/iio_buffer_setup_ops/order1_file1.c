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
	int err;
	err = ldv_function();
	if(err){
		return IRQ_HANDLED;
	}
	if(deg_lock == 0){
		mutex_lock(ldv_envgen);
		deg_lock = 1;
	}
	return IRQ_WAKE_THREAD;
}

static irqreturn_t irq_handler2(int irq_id, void * data){
	if(deg_lock == 1){
		deg_lock = 0;
		mutex_unlock(ldv_envgen);
	}
	return IRQ_HANDLED;
}

static int __init ldv_init(void)
{
	deg_lock = 0;
	int err;
	err = iio_triggered_buffer_setup(dev, irq_handler1, irq_handler2, NULL);
	if (err) {
		return err;
	}
	return 0;
}

static void __exit ldv_exit(void)
{
	iio_triggered_buffer_cleanup(dev);
	if(deg_lock==1){
		mutex_unlock(ldv_envgen);
	}
}

module_init(ldv_init);
module_exit(ldv_exit);

