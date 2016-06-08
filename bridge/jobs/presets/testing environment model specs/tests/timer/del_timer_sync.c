#include <linux/module.h>
#include <linux/timer.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

struct timer_list ldv_timer;
unsigned long expires;

void ldv_handler(unsigned long data)
{
	ldv_invoke_callback();
}

static int __init ldv_init(void)
{
    int flip_a_coin;

	setup_timer(&ldv_timer, ldv_handler, 0);
	flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        if (!mod_timer(&ldv_timer, jiffies + msecs_to_jiffies(200))) {
            del_timer_sync(&ldv_timer);
            ldv_deregister();
        }
    }
    return 0;
}

static void __exit ldv_exit(void)
{
    /* pass */
}

module_init(ldv_init);
module_exit(ldv_exit);