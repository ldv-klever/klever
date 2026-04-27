/*
 * Copyright (c) 2020 ISP RAS (http://www.ispras.ru)
 * Ivannikov Institute for System Programming of the Russian Academy of Sciences
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <linux/types.h>
#include <linux/device.h>
#include <ldv/linux/list.h>
#include <ldv/linux/common.h>
#include <ldv/linux/device.h>
#include <ldv/linux/slab.h>
#include <ldv/verifier/color_memory.h>
#include <ldv/verifier/nondet.h>
#include <ldv/linux/err.h>
#include <ldv/verifier/common.h>

#include <linux/idr.h>
#include <linux/workqueue.h>
#include <linux/llist.h>
#include <drm/drm_device.h>
#include <drm/drm_modes.h>
#include <drm/drm_mode_config.h>
#include <drm/drm_managed.h>
#include <drm/drm_encoder.h>
#include <drm/drm_crtc.h>
#include <drm/drm_plane.h>

extern struct ldv_devres *ldv_color_devm_kmalloc(size_t size, gfp_t gfp);
extern void ldv_color_devm_kfree(struct ldv_devres *dr);

extern void *ldv_color_drm_kmalloc(size_t size, gfp_t gfp);
extern void ldv_color_drm_kfree(struct ldv_drmres *dr);
extern void ldv_color_drm_dev_kfree(struct drm_device *dev);

/*
 * The following structures are defined in the kernel
 * ".c" files, so they replaced with local ones.
 */
// Corresponds to the struct devres_node
struct ldv_devres_node {
	struct list_head entry;
	dr_release_t release;
	const char *name;
	size_t size;
};

// Corresponds to the struct devres
struct ldv_devres {
	struct ldv_devres_node node;
	u8 data[];
};

// Corresponds to the struct drmres_node
struct ldv_drmres_node {
	struct list_head entry;
	drmres_release_t release;
	const char *name;
	size_t size;
};

// Corresponds to the struct drmres
struct ldv_drmres {
	struct ldv_drmres_node node;
	u8 data[];
};


struct drm_device *drm_dev;

unsigned int ldv_is_memory_alloc_failures = 1;

void *ldv_color_drm_kmalloc_wrapper(size_t size, gfp_t gfp)
{
	void *res;

	if (ldv_is_memory_alloc_failures && ldv_undef_int())
		return NULL;

	/* Always successful according to SV-COMP definition. */
	res = ldv_color_drm_kmalloc(size, gfp);
	ldv_assume(res != NULL);

	return res;
}

void *ldv_color_devm_kmalloc_wrapper(size_t size, gfp_t gfp)
{
	void *res;

	if (ldv_is_memory_alloc_failures && ldv_undef_int())
		return NULL;

	/* Always successful according to SV-COMP definition. */
	res = ldv_color_devm_kmalloc(size, gfp);
	ldv_assume(res != NULL);

	return res;
}

int ldv_drmm_mode_config_init(struct drm_device *dev)
{
	INIT_LIST_HEAD(&dev->mode_config.crtc_list);
	INIT_LIST_HEAD(&dev->mode_config.encoder_list);
	INIT_LIST_HEAD(&dev->mode_config.plane_list);

	if (ldv_is_memory_alloc_failures && ldv_undef_int())
		return 12;
	else
		return 0;
}

void ldv_drm_mode_config_cleanup(struct drm_device *dev)
{
	struct drm_crtc *crtc, *ct;
	struct drm_encoder *encoder, *enct;
	struct drm_plane *plane, *plt;

	list_for_each_entry_safe(encoder, enct, &dev->mode_config.encoder_list,
							 head) {
		encoder->funcs->destroy(encoder);
	}

	list_for_each_entry_safe(plane, plt, &dev->mode_config.plane_list,
							 head) {
		plane->funcs->destroy(plane);
	}

	list_for_each_entry_safe(crtc, ct, &dev->mode_config.crtc_list, head) {
		crtc->funcs->destroy(crtc);
	}
}

void ldv_drm_crtc_cleanup(struct drm_crtc *crtc)
{
	struct drm_device *dev = crtc->dev;

	ldv_list_del(&crtc->head);
}

int ldv_drm_crtc_init_with_planes(struct drm_device *dev,
								  struct drm_crtc *crtc,
								  const struct drm_crtc_funcs *funcs)
{
	struct drm_mode_config *config = &dev->mode_config;

	crtc->dev = dev;
	crtc->funcs = funcs;
	ldv_list_add(&crtc->head, config->crtc_list.prev, &config->crtc_list);
	return 0;
}

void ldv_drm_plane_cleanup(struct drm_plane *plane)
{
	struct drm_device *dev = plane->dev;

	ldv_list_del(&plane->head);
}

int ldv_drm_universal_plane_init(struct drm_device *dev,
								 struct drm_plane *plane,
								 const struct drm_plane_funcs *funcs)
{
	struct drm_mode_config *config = &dev->mode_config;

	plane->dev = dev;
	plane->funcs = funcs;
	ldv_list_add(&plane->head, config->plane_list.prev, &config->plane_list);
	return 0;
}

void ldv_drm_encoder_cleanup(struct drm_encoder *encoder)
{
	struct drm_device *dev = encoder->dev;

	ldv_list_del(&encoder->head);
}

int ldv_drm_encoder_init(struct drm_device *dev, struct drm_encoder *encoder,
						 const struct drm_encoder_funcs *funcs)
{
	encoder->dev = dev;
	encoder->funcs = funcs;
	ldv_list_add(&encoder->head, dev->mode_config.encoder_list.prev, &dev->mode_config.encoder_list);
	return 0;
}

static const struct drm_encoder_funcs ldv_drm_simple_encoder_funcs_cleanup = {
	.destroy = ldv_drm_encoder_cleanup,
};

int ldv_drm_simple_encoder_init(struct drm_device *dev,
								struct drm_encoder *encoder)
{
	return ldv_drm_encoder_init(dev, encoder,
								&ldv_drm_simple_encoder_funcs_cleanup);
}


void ldv_devres_dev_set_drvdata(struct device *dev, void *data)
{
	dev->driver_data = data;
}

void *ldv_devm_kmalloc(struct device *dev, size_t size, gfp_t gfp)
{
	struct ldv_devres *dr;

	dr = ldv_color_devm_kmalloc_wrapper(size + sizeof(struct ldv_devres), gfp);
	if (!dr)
		return NULL;

	// Add new node to te ldv_devres list of the device

	INIT_LIST_HEAD(&dr->node.entry);
	ldv_list_add(&dr->node.entry, dev->devres_head.prev, &dev->devres_head);

	return dr->data;
}

void *ldv_devm_kzalloc(struct device *dev, size_t size, gfp_t gfp)
{
	struct ldv_devres *dr;

	dr = ldv_color_devm_kmalloc_wrapper(size + sizeof(struct ldv_devres), gfp);
	if (!dr)
		return NULL;

	memset(dr, 0, offsetof(struct ldv_devres, data));

	// Add new node to te ldv_devres list of the device

	INIT_LIST_HEAD(&dr->node.entry);
	ldv_list_add(&dr->node.entry, dev->devres_head.prev, &dev->devres_head);

	return dr->data;
}

int ldv_devres_release_all(struct device *dev)
{
	struct ldv_devres *dr, *tmp;

	if (ldv_list_empty(&dev->devres_head))
		return 0;

	list_for_each_entry_safe_reverse(dr, tmp, &dev->devres_head, node.entry) {
		ldv_color_devm_kfree(dr);
	}

	return 0;
}

void ldv_devm_kfree(struct device *dev, const void *p)
{
	struct ldv_devres *dr_free = NULL, *dr;
	struct ldv_devres_node *node;

	if (!p)
		return;

	// Look for the *p node in the ldv_devres list
	// of the device this memory belongs to

	list_for_each_entry_reverse(node, &dev->devres_head, entry) {
		dr = container_of(node, struct ldv_devres, node);

		if (dr->data == p) {
			dr_free = dr;
			break;
		}
	}

	// Release if found

	if (dr_free) {
		list_del_init(&dr_free->node.entry);
		ldv_color_devm_kfree(dr_free);
	}
}


static struct ldv_drmres *ldv_drmm_alloc_dr(drmres_release_t release,
										 size_t size, gfp_t gfp, int flag)
{
	struct ldv_drmres *dr;

	dr = ldv_color_drm_kmalloc_wrapper(size + sizeof(*dr), gfp);
	if (!dr)
		return NULL;

	if (flag)
		memset(dr, 0, offsetof(struct ldv_drmres, data));

	INIT_LIST_HEAD(&dr->node.entry);
	dr->node.release = release;
	dr->node.size = size;
	return dr;
}

void *ldv_drmm_kmalloc(struct drm_device *dev, size_t size, gfp_t gfp)
{
	struct ldv_drmres *dr;

	dr = ldv_drmm_alloc_dr(NULL, size, gfp, 0);
	if (!dr)
		return NULL;

	ldv_list_add(&dr->node.entry, &dev->managed.resources, dev->managed.resources.next);

	return dr->data;
}

void *ldv_drmm_kzalloc(struct drm_device *dev, size_t size, gfp_t gfp)
{
	struct ldv_drmres *dr;

	dr = ldv_drmm_alloc_dr(NULL, size, gfp, 1);
	if (!dr)
		return NULL;

	ldv_list_add(&dr->node.entry, &dev->managed.resources, dev->managed.resources.next);

	return dr->data;
}

void ldv_drm_managed_release(struct drm_device *dev)
{
	struct ldv_drmres *dr, *tmp;

	list_for_each_entry_safe(dr, tmp, &dev->managed.resources, node.entry) {
		if (dr->node.release)
			dr->node.release(dev, dr->node.size ? *(void **)&dr->data : NULL);

		ldv_list_del(&dr->node.entry);
		ldv_color_drm_kfree(dr);
	}
}

void ldv_drmm_add_final_kfree(struct drm_device *dev, void *container)
{
	dev->managed.final_kfree = container;
}

int __ldv_drmm_add_action(struct drm_device *dev,
						  drmres_release_t action,
						  void *data)
{
	struct ldv_drmres *dr;

	dr = ldv_drmm_alloc_dr(action, 0, GFP_KERNEL, 0);
	if (!dr)
		return -1;

	ldv_list_add(&dr->node.entry, &dev->managed.resources, dev->managed.resources.next);

	return 0;
}

int __ldv_drmm_add_action_or_reset(struct drm_device *dev,
								   drmres_release_t action,
								   void *data)
{
	int ret;

	ret = __ldv_drmm_add_action(dev, action, data);
	if (ret)
		action(dev, data);

	return ret;
}

void ldv_drmm_kfree(struct drm_device *dev, void *data)
{
	struct ldv_drmres *dr_match = NULL, *dr;

	if (!data)
		return;

	list_for_each_entry(dr, &dev->managed.resources, node.entry) {
		if (dr->data == data) {
			dr_match = dr;
			break;
		}
	}
	if (dr_match) {
		ldv_list_del(&dr_match->node.entry);
		ldv_color_drm_kfree(dr_match);
	}
}


void ldv_kref_init(struct kref *kref)
{
	kref->refcount.refs.counter = 1;
}

struct device *ldv_get_device(struct device *dev)
{
	struct kobject *kobj = &dev->kobj;
	struct kref *kref = &kobj->kref;

	kref->refcount.refs.counter = kref->refcount.refs.counter + 1;
	return dev;
}

void ldv_put_device(struct device *dev)
{
	struct kobject *kobj = &dev->kobj;
	struct kref *kref = &kobj->kref;

	kref->refcount.refs.counter = kref->refcount.refs.counter - 1;
}

static void ldv_drm_dev_init_release(struct drm_device *dev, void *res)
{
	ldv_put_device(dev->dev);
	dev->dev = NULL;
}

static int ldv_drm_dev_init(struct drm_device *dev,
							const struct drm_driver *driver,
							struct device *parent)
{
	int ret = 0;

	ldv_kref_init(&dev->ref);
	dev->dev = ldv_get_device(parent);

	INIT_LIST_HEAD(&dev->managed.resources);

	ret = __ldv_drmm_add_action_or_reset(dev, ldv_drm_dev_init_release, NULL);

	return ret;
}

struct drm_device *ldv_drm_dev_alloc(struct drm_driver *driver,
									 struct device *parent)
{
	struct drm_device *dev;
	int ret = 0;

	dev = ldv_color_drm_kmalloc_wrapper(sizeof(*dev), GFP_KERNEL);
	if (!dev)
		return ldv_err_ptr(12);
	drm_dev = dev;

	ldv_devres_dev_set_drvdata(parent, dev);

	ret = ldv_drm_dev_init(dev, driver, parent);
	if (ret) {
		ldv_color_drm_dev_kfree(dev);
		parent->driver_data = NULL;
		return ldv_err_ptr(12);
	}

	ldv_drmm_add_final_kfree(dev, dev);

	if (ldv_is_err(dev)) {
		ldv_drm_managed_release(dev);
		ldv_color_drm_dev_kfree(dev->managed.final_kfree);
		parent->driver_data = NULL;
	}

	return dev;
}

static void ldv_drm_dev_release(struct kref *ref)
{
	struct drm_device *dev = container_of(ref, struct drm_device, ref);
	struct device *parent;

	if (drm_dev) {
		parent = dev->dev;
		ldv_drm_managed_release(dev);
		ldv_color_drm_dev_kfree(dev->managed.final_kfree);
		parent->driver_data = NULL;
	}
}

int ldv_kref_put(struct kref *kref, void (*release)(struct kref *kref))
{
	kref->refcount.refs.counter = kref->refcount.refs.counter - 1;
	if (!(kref->refcount.refs.counter)) {
		release(kref);
		return 1;
	}
	return 0;
}

void ldv_drm_dev_put(struct drm_device *dev)
{
	if (dev)
		ldv_kref_put(&dev->ref, ldv_drm_dev_release);
}

void *__ldv_devm_drm_dev_alloc(struct device *parent, struct drm_driver *driver, size_t size, size_t offset)
{
	void *container;
	struct drm_device *dev;
	int ret = 0;

	container = ldv_color_drm_kmalloc_wrapper(size, GFP_KERNEL);
	if (!container)
		return ldv_err_ptr(12);
	dev = container + offset;
	drm_dev = dev;

	if (parent->driver_data)
		ldv_drm_dev_put(ldv_devres_dev_get_drvdata(parent));
	ldv_devres_dev_set_drvdata(parent, dev);

	ret = ldv_drm_dev_init(dev, driver, parent);
	if (ret) {
		ldv_color_drm_dev_kfree(container);
		parent->driver_data = NULL;
		return ldv_err_ptr(12);
	}

	ldv_drmm_add_final_kfree(dev, container);

	if (ldv_is_err(container)) {
		ldv_drm_managed_release(dev);
		ldv_color_drm_dev_kfree(dev->managed.final_kfree);
		parent->driver_data = NULL;
	}

	return container;
}

const void *ldv_devres_of_device_get_match_data(const struct device *dev)
{
	int ret = 1;
	return ret;
}
