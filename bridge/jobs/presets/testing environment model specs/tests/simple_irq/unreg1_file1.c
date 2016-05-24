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
	free_irq(irq_id, data);
	deg_lock = 1;
};

static struct ldvdriver driver = {
	.handler =	handler
};

static int __init ldv_init(void)
{
	deg_lock = 0;
	int err;
	err = request_irq(irq_id, irq_handler1,0, "ldv interrupt", data);
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

