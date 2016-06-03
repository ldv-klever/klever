#include <linux/module.h>
#include <linux/interrupt.h>
#include <linux/irqreturn.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

unsigned int irq_id = 100;
void *data;
struct device *dev;
int flip_a_coin;

static irqreturn_t irq_handler(int irq_id, void * data){
	ldv_invoke_callback();
    return IRQ_HANDLED;
}

static irqreturn_t irq_thread(int irq_id, void * data){
    ldv_invoke_callback();
}

static int __init ldv_init(void)
{
    flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        return devm_request_threaded_irq(dev, irq_id,irq_handler, irq_thread, NULL, "ldv interrupt", data);
    }
    return 0;
}

static void __exit ldv_exit(void)
{
	if (flip_a_coin) {
        devm_free_irq(dev, irq_id, data);
        ldv_deregister();
    }
}

module_init(ldv_init);
module_exit(ldv_exit);

