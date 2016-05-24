#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/interrupt.h>
#include <linux/irqreturn.h>
#include <linux/iio/iio.h>
#include <linux/iio/buffer.h>
#include <linux/iio/trigger_consumer.h>
#include <linux/iio/triggered_buffer.h>

struct mutex *ldv_envgen;
static int ldv_function(void);
struct iio_dev * dev;
int deg_lock;

static int buffer_preenable(struct iio_dev *indio_dev){
	int ret;
	ret = ldv_function();
	if(ret){
		return ret;
	}
	mutex_lock(ldv_envgen);
	return ret;
}

static int buffer_postenable(struct iio_dev *indio_dev){
	mutex_unlock(ldv_envgen);
	int ret = ldv_function();
	return ret;
}

static int buffer_predisable(struct iio_dev *indio_dev){
	mutex_lock(ldv_envgen);
}

static int buffer_postdisable(struct iio_dev *indio_dev){
	mutex_unlock(ldv_envgen);
}

static const struct iio_buffer_setup_ops buffer_setup_ops = {
          .preenable = &buffer_preenable,
          .postenable = &buffer_postenable,
          .predisable = &buffer_predisable,
          .postdisable = &buffer_postdisable,
};

static int __init ldv_init(void)
{
	int err;
	err = iio_triggered_buffer_setup(dev, NULL, NULL, &buffer_setup_ops);
	if (err) {
		return err;
	}
	return 0;
}

static void __exit ldv_exit(void)
{
	iio_triggered_buffer_cleanup(dev);
}

module_init(ldv_init);
module_exit(ldv_exit);
