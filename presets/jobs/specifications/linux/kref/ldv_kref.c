#include <linux/kobject.h>
#include <linux/types.h>
#include <linux/kref.h>
#include <linux/refcount.h>
#include <ldv/common.h>
#include <ldv/verifier/common.h>
#include <linux/kernel.h>
#include <media/v4l2-device.h>
#include <linux/usb.h>
#include <linux/device.h>
#include <ldv/linux/device.h>
#include <ldv/linux/slab.h>
#include <ldv/linux/kref.h>


void ldv_kobject_release(struct kref *kref)
{
	struct kobject *kobj = container_of(kref, struct kobject, kref);
	kobj->ktype->release(kobj);
}

void ldv_kobject_put(struct kobject *kobj)
{
	if (kobj)
		ldv_kref_put(&kobj->kref, ldv_kobject_release);
}

struct kobject *ldv_kobject_get(struct kobject *kobj)
{
	if (kobj)
		ldv_kref_get(&kobj->kref);
	return kobj;
}

void ldv_kobject_init_internal(struct kobject *kobj)
{
	if (!kobj)
		return;

	ldv_kref_init(&kobj->kref);
	kobj->state_in_sysfs = 0;
	kobj->state_add_uevent_sent = 0;
	kobj->state_remove_uevent_sent = 0;
	kobj->state_initialized = 1;
}

void ldv_kobject_init(struct kobject *kobj, struct kobj_type *ktype)
{
	ldv_kobject_init_internal(kobj);
	kobj->ktype = ktype;
	return;
}

void ldv_put_device(struct device *dev)
{
	if (dev)
		ldv_kobject_put(&dev->kobj);
}

struct device *ldv_kobj_to_dev(struct kobject *kobj)
{
	return container_of(kobj, struct device, kobj);
}

struct device *ldv_get_device(struct device *dev)
{
	return dev ? ldv_kobj_to_dev(ldv_kobject_get(&dev->kobj)) : NULL;
}

struct usb_device *ldv_usb_get_dev(struct usb_device *dev)
{
	if (dev)
		ldv_get_device(&dev->dev);
	return dev;
}

void ldv_usb_put_dev(struct usb_device *dev)
{
	if (dev)
		ldv_put_device(&dev->dev);
}

void ldv_v4l2_prio_init(struct v4l2_prio_state *global)
{
	memset(global, 0, sizeof(*global));
}

int ldv_v4l2_device_register(struct device *dev, struct v4l2_device *v4l2_dev)
{
	if (v4l2_dev == NULL)
		return -EINVAL;

	ldv_v4l2_prio_init(&v4l2_dev->prio);
	ldv_kref_init(&v4l2_dev->ref);
	ldv_get_device(dev);
	v4l2_dev->dev = dev;
	ldv_dev_set_drvdata(dev, v4l2_dev);

	return 0;
}

void ldv_video_device_release(struct video_device *vdev)
{
	kfree(vdev);
}

struct video_device *ldv_video_device_alloc(void)
{
	return ldv_kzalloc(sizeof(struct video_device), GFP_KERNEL);
}

void ldv_v4l2_device_release(struct kref *kref)
{
	struct v4l2_device *v4l2_dev = container_of(kref, struct v4l2_device, ref);
	v4l2_dev->release(v4l2_dev);
}

int ldv_v4l2_device_put(struct v4l2_device *v4l2_dev)
{
	return ldv_kref_put(&v4l2_dev->ref, ldv_v4l2_device_release);
}

void ldv_v4l2_device_disconnect(struct v4l2_device *v4l2_dev)
{
	if (v4l2_dev->dev == NULL)
		return;

	if (ldv_dev_get_drvdata(v4l2_dev->dev) == v4l2_dev)
		ldv_dev_set_drvdata(v4l2_dev->dev, NULL);

	ldv_put_device(v4l2_dev->dev);
	v4l2_dev->dev = NULL;
}

void ldv_usb_set_intfdata(struct usb_interface *intf, void *data)
{
	ldv_dev_set_drvdata(&intf->dev, data);
}

void ldv_video_get(struct video_device *vdev)
{
	ldv_get_device(&vdev->dev);
}

void ldv_video_put(struct video_device *vdev)
{
	ldv_put_device(&vdev->dev);
}
