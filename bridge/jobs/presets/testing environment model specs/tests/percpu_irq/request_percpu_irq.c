#include <linux/module.h>
#include <linux/interrupt.h>
#include <linux/irqreturn.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

unsigned int irq_id = 100;
void __percpu *percpu_dev_id;
int flip_a_coin;

static irqreturn_t irq_handler(int irq_id, void * data){
	ldv_invoke_callback();
	return IRQ_HANDLED;
}

static int __init ldv_init(void)
{
	flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        return request_percpu_irq(irq_id, irq_handler, "ldv_dev", percpu_dev_id);
    }
    return 0;
}

static void __exit ldv_exit(void)
{
	if (flip_a_coin) {
        free_percpu_irq(irq_id, percpu_dev_id);
        ldv_deregister();
    }
}

module_init(ldv_init);
module_exit(ldv_exit);





