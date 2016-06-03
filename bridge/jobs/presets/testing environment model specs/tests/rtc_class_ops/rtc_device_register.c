#include <linux/init.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <linux/vmalloc.h>
#include <linux/rtc.h>

struct mutex *ldv_envgen;
static int ldv_function(void);
struct device *dev;
struct rtc_device *rtc;
int deg_lock;

struct ldvdriver {
	void (*handler)(void);
};

static int ldvgettime(struct device *dev, struct rtc_time *tm)
{
	if(deg_lock){
		mutex_lock(ldv_envgen);
	}
}

static int ldvsettime(struct device *dev, struct rtc_time *tm)
{
	if(deg_lock){
		mutex_lock(ldv_envgen);
	}
}

static const struct rtc_class_ops ldv_ops = {
	.read_time = ldvgettime,
	.set_time = ldvsettime,
};

static void handler(void)
{
	rtc_device_unregister(rtc);
	deg_lock = 1;
};

static struct ldvdriver driver = {
	.handler =	handler
};

static int __init ldv_init(void)
{
	deg_lock = 0;
	rtc = rtc_device_register("rtc-ldv", &dev, &ldv_ops,THIS_MODULE);
	if (IS_ERR(rtc))
		return PTR_ERR(rtc);
	return 0;
}

static void __exit ldv_exit(void)
{
	//nothing
}

module_init(ldv_init);
module_exit(ldv_exit);
