#include <linux/module.h>
#include <linux/interrupt.h>
#include <linux/irqreturn.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

unsigned int irq_id = 100;
void __percpu *percpu_dev_id;

static irqreturn_t irq_handler(int irq_id, void * data){
	ldv_invoke_reached();
	return IRQ_HANDLED;
}

static int __init ldv_init(void)
{
	return request_percpu_irq(irq_id, irq_handler, "ldv_dev", percpu_dev_id);
}

static void __exit ldv_exit(void)
{
	free_percpu_irq(irq_id, percpu_dev_id);
}

module_init(ldv_init);
module_exit(ldv_exit);

