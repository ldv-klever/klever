#include <linux/module.h>
#include <linux/timer.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

int flip_a_coin;
struct timer_list ldv_timer;
unsigned long data;

void ldv_handler(unsigned long data)
{
	ldv_invoke_callback();
}

static int __init ldv_init(void)
{
	setup_timer(&ldv_timer, ldv_handler, data);
	flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        return mod_timer(&ldv_timer, jiffies + msecs_to_jiffies(200));
    }
    return 0;
}

static void __exit ldv_exit(void)
{
	if (flip_a_coin) {
        del_timer(&ldv_timer);
        ldv_deregister();
    }
}

module_init(ldv_init);
module_exit(ldv_exit);