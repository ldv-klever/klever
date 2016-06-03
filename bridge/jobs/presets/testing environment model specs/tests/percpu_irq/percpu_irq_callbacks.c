#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/interrupt.h>
#include <linux/irqreturn.h>

struct mutex *ldv_envgen;
static int ldv_function(void);
unsigned int irq_id = 100;
void * data;
void __percpu *percpu_dev_id;
struct device *dev;
const char *devname;
int deg_lock;

static irqreturn_t irq_handler1(int irq_id, void * data){
	int err;
	err = ldv_function();
	if(err){
		return err;
	}
	if(deg_lock==1){
		mutex_unlock(ldv_envgen);
	}
	mutex_lock(ldv_envgen);
	deg_lock = 1;
	return IRQ_HANDLED;
}

static int __init ldv_init(void)
{
	deg_lock = 0;
	int err;
	err = request_percpu_irq(irq_id, irq_handler1, devname, percpu_dev_id);
	if (err) {
		return err;
	}
	return 0;
}

static void __exit ldv_exit(void)
{
	free_percpu_irq(irq_id, percpu_dev_id);
	if(deg_lock==1){
		mutex_unlock(ldv_envgen);
	}
}

module_init(ldv_init);
module_exit(ldv_exit);

