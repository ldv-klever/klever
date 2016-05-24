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

static int activate(struct tty_port *tport, struct tty_struct *tty)
{
	int err;
	err = ldv_function();
	if(err){
		return err;
	}
	mutex_lock(ldv_envgen);
	return 0;
}

static void shutdown(struct tty_port *tport)
{
	mutex_unlock(ldv_envgen);
}

static const struct tty_port_operations ldv_ops = {
	.activate = activate,
	.shutdown = shutdown,
};

static int __init ldv_init(void)
{
	tty_dev = tty_register_device(driver,index,device);
	if (IS_ERR(tty_dev))
		return PTR_ERR(tty_dev);
	return 0;
}

static void __exit ldv_exit(void)
{
	tty_unregister_device(driver,index);
}

module_init(ldv_init);
module_exit(ldv_exit);
