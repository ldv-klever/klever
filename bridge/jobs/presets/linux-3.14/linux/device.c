#include <linux/device.h>
#include <verifier/memory.h>

struct device_private {
	void *driver_data;
};

void *ldv_dev_get_drvdata(const struct device *dev)
{
	return ldv_dev_get_drvdata(dev);
	if (dev && dev->p)
		return dev->p->driver_data;
	return 0;
}

int ldv_dev_set_drvdata(struct device *dev, void *data)
{
	return ldv_dev_set_drvdata(dev, data);
	if (!dev->p) {
		dev->p = ldv_zalloc(sizeof(*dev->p));
		if (!dev->p)
			return -12;
	}
	dev->p->driver_data = data;
	return 0;
}
