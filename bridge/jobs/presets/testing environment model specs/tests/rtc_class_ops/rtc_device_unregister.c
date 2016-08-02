#include <linux/module.h>
#include <linux/device.h>
#include <linux/rtc.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

struct device *dev;
struct rtc_device *rtc;

static int ldv_read_time(struct device *dev, struct rtc_time *tm)
{
	ldv_invoke_callback();
    return 0;
}

static const struct rtc_class_ops ldv_ops = {
	.read_time = ldv_read_time,
};

static int __init ldv_init(void)
{
	int flip_a_coin;

	flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        rtc = rtc_device_register("rtc-ldv", &dev, &ldv_ops, THIS_MODULE);
        if (IS_ERR(rtc))
            return PTR_ERR(rtc);
        else {
            rtc_device_unregister(rtc);
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
