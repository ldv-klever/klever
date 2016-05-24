#include <linux/kernel.h>
#include <linux/module.h>

struct mutex *ldv_envgen;
static int ldv_function(void);

struct ldv_type {
	int (*probe)(void);
	void (*disconnect)(void);
};

int ldv_probe(void)
{
	int ret;
	ret = ldv_function();
	if(ret){
		return ret;
	}
	mutex_lock(ldv_envgen);
	return 0;
}

static void ldv_disconnect(void)
{
	mutex_unlock(ldv_envgen);
}

static struct ldv_type ldv_driver = {
	.probe =		ldv_probe,
	.disconnect =	ldv_disconnect,
};

static int __init ldv_init(void)
{
	int ret;
	ret = ldv_function();
	if(ret){
		return ret;
	}
}

module_init(ldv_init);
//module_exit(module_exit);
