#include <linux/init.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <linux/vmalloc.h>
#include <linux/device-mapper.h>
#include <linux/tty.h>
#include <linux/tty_driver.h>
#include <linux/tty_flip.h>

struct device * tty_dev;
struct tty_driver *driver;
unsigned index;
struct device *device;
struct mutex *ldv_envgen;
static int ldv_function(void);
int deg_lock;

struct ldvdriver {
	void (*handler)(void);
};

static int activate(struct tty_port *tport, struct tty_struct *tty)
{
	if(deg_lock){
		mutex_lock(ldv_envgen);
	}
	int err;
	err = ldv_function();
	if(err){
		return err;
	}
	return 0;
}

static void shutdown(struct tty_port *tport)
{
	if(deg_lock){
		mutex_lock(ldv_envgen);
	}
}

static const struct tty_port_operations ldv_ops = {
	.activate = activate,
	.shutdown = shutdown,
};

static void handler(void)
{
	tty_unregister_device(driver,index);
	deg_lock = 1;
};

static struct ldvdriver ldvdriver = {
	.handler =	handler
};

static int __init ldv_init(void)
{
	deg_lock = 0;
	tty_dev = tty_register_device(driver,index,device);
	if (IS_ERR(tty_dev))
		return PTR_ERR(tty_dev);
	return 0;
}

static void __exit ldv_exit(void)
{
	//nothing
}

module_init(ldv_init);
module_exit(ldv_exit);
