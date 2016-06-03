#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/usb.h>

struct mutex *ldv_envgen;
static int ldv_function(void);

struct ldvdriver {
	int (*probe)(void);
	void (*disconnect)(void);
};

int probe_func(void){
	return ldv_function();
}

int disconnect_func(void){
	//nothing
}

static struct ldvdriver ldv_driver = {
	.probe = probe_func,
	.disconnect = disconnect_func,
};

static int __init ldv_init(void)
{
	int res;
	res = ldv_function();
	if(res)
		return res;
	mutex_lock(ldv_envgen);
	return res;
}

static void __exit ldv_exit(void)
{
	mutex_unlock(ldv_envgen);
}

module_init(ldv_init);
module_exit(ldv_exit);
