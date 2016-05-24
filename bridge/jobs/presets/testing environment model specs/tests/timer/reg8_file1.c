#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/timer.h>

struct mutex *ldv_envgen;
static int ldv_function(void);
static struct timer_list my_timer;
int deg_lock = 0;
unsigned long expires;

void my_timer_callback(unsigned long data)
{
	if(deg_lock == 0){
		int ret = mod_timer(&my_timer, expires);
		if(ret == 0){
			mutex_lock(ldv_envgen);
			deg_lock++;
		}
	}
	else{
		mutex_lock(ldv_envgen);
	}
}

static int __init ldv_init(void)
{
	int ret;
	setup_timer( &my_timer, my_timer_callback, 0 );
	ret = mod_timer( &my_timer, jiffies + msecs_to_jiffies(200) );
	if (ret) {
		return ret;
	}
	return 0;
}

static void __exit ldv_exit(void)
{
	del_timer( &my_timer );
	if(deg_lock > 0){
		mutex_unlock(ldv_envgen);
	}
}

module_init(ldv_init);
module_exit(ldv_exit);