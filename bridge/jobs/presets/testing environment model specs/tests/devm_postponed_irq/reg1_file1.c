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
	mutex_lock(ldv_envgen);
	return IRQ_HANDLED;
}

static int __init ldv_init(void)
{
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
}

module_init(ldv_init);
module_exit(ldv_exit);

