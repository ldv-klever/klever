#include <linux/module.h>
#include <linux/interrupt.h>
#include <linux/irqreturn.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

unsigned int irq_id = 100;
void * data;

static irqreturn_t irq_handler(int irq_id, void * data)
{
	ldv_invoke_reached();
	return IRQ_HANDLED;
}

static int __init ldv_init(void)
{
	return request_irq(irq_id, irq_handler, 0, "ldv interrupt", data);
}

static void __exit ldv_exit(void)
{
	free_irq(irq_id, data);
}

module_init(ldv_init);
module_exit(ldv_exit);

