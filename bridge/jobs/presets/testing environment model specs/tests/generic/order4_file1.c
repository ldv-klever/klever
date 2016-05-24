#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/usb.h>

struct mutex *ldv_envgen;
static int ldv_function(void);

struct ldvdriver {
	char *name;
	int (*probe)(void);
	void (*disconnect)(void);
};

static struct ldvdriver ldv_driver = {
	.name = "simple"
};

static int __init ldv_init(void)
{
	int res;
	res = ldv_function();
	return res;
}

static void __exit ldv_exit(void)
{
	//nothing
}

module_init(ldv_init);
module_exit(ldv_exit);
