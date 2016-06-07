#include <linux/module.h>
#include <linux/interrupt.h>
#include <linux/irqreturn.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

unsigned int irq_id = 100;
void *data;
struct device *dev;

static irqreturn_t irq_handler(int irq_id, void * data)
{
    return IRQ_WAKE_THREAD;
}

static irqreturn_t irq_thread(int irq_id, void * data)
{
    ldv_invoke_reached();
    return IRQ_HANDLED;
}

static int __init ldv_init(void)
{
    return devm_request_threaded_irq(dev, irq_id, irq_handler, irq_thread, NULL, "ldv interrupt", data);
}

static void __exit ldv_exit(void)
{
    devm_free_irq(dev, irq_id, data);
}

module_init(ldv_init);
module_exit(ldv_exit);

