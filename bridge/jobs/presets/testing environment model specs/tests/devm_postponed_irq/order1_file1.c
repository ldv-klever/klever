#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/interrupt.h>
#include <linux/irqreturn.h>

struct mutex *ldv_envgen;
static int ldv_function(void);
unsigned int irq_id = 100;
void * data;
void __percpu * percpu_dev_id;
struct device * dev;
const char *devname;
int deg_lock;

static irqreturn_t irq_handler1(int irq_id, void * data){
	int err;
	err = ldv_function();
	if(err){
		return IRQ_HANDLED;
	}
	if(deg_lock==0){
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
	return IRQ_WAKE_THREAD;
}

static int __init ldv_init(void)
{
	deg_lock = 0;
	int err;
	err = devm_request_threaded_irq(dev, irq_id,irq_handler1, NULL , 0, "ldv interrupt", data);
	if (err) {
		return err;
	}
	return 0;
}

static void __exit ldv_exit(void)
{
	devm_free_irq(dev, irq_id, data);
	if(deg_lock==1){
		mutex_unlock(ldv_envgen);
	}
}

module_init(ldv_init);
module_exit(ldv_exit);

