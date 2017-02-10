#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>

static DEFINE_MUTEX(my_mutex);

int gvar;

struct my_struct {
    int (*func)(void);
    int (*gunc)(void);
};

int f(void) {
	mutex_lock(&my_mutex);
	gvar = 1;
	mutex_unlock(&my_mutex);
	return 0;
}

void g(void) {
	int b;
	mutex_lock(&my_mutex);
	b = gvar;
	mutex_unlock(&my_mutex);
}

struct my_struct my_driver = {
    .func = f,
    .gunc = g
};

static int __init init(void)
{
    return 0;
}

module_init(init);