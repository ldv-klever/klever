#include <linux/module.h>
#include <linux/timer.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

int flip_a_coin;
struct timer_list ldv_timer;
unsigned long data;

void ldv_handler(unsigned long data)
{
	ldv_invoke_reached();
}

static int __init ldv_init(void)
{
	ldv_timer.function = ldv_handler;
	ldv_timer.data = data;
	init_timer(&ldv_timer);
	return mod_timer(&ldv_timer, jiffies + msecs_to_jiffies(200));
}

static void __exit ldv_exit(void)
{
	del_timer(&ldv_timer);
}

module_init(ldv_init);
module_exit(ldv_exit);