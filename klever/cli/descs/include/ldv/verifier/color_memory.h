/*
 * Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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

#ifndef __LDV_LINUX_COLOR_MEMORY_H
#define __LDV_LINUX_COLOR_MEMORY_H

#include <linux/types.h>

struct device;

extern struct drm_device;
struct drm_driver;
struct platform_device;
struct drm_crtc;
struct drm_crtc_funcs;
struct drm_plane;
struct drm_plane_funcs;
struct drm_encoder;
struct drm_encoder_funcs;

extern void *ldv_dev_get_drvdata(const struct device *dev);
extern int ldv_dev_set_drvdata(struct device *dev, void *data);
extern void *ldv_devm_kmalloc(struct device *dev, size_t size, gfp_t gfp);
extern void *ldv_devm_kzalloc(struct device *dev, size_t size, gfp_t gfp);
extern void *ldv_devm_kmalloc_array(struct device *dev, size_t n, size_t size, gfp_t flags);
extern void *ldv_devm_kcalloc(struct device *dev, size_t n, size_t size, gfp_t flags);
extern void ldv_devm_kfree(struct device *dev, const void *p);

extern void *ldv_drmm_kmalloc(struct drm_device *dev, size_t size, gfp_t gfp);
extern void *ldv_drmm_kzalloc(struct drm_device *dev, size_t size, gfp_t gfp);

extern int ldv_kref_put(struct kref *kref, void (*release)(struct kref *kref));
extern void ldv_drm_dev_put(struct drm_device *dev);
extern void ldv_kref_init(struct kref *kref);
extern struct device *ldv_get_device(struct device *dev);
extern void ldv_put_device(struct device *dev);
extern struct drm_device *ldv_drm_dev_alloc(struct drm_driver *driver, struct device *parent);

extern void ldv_devres_platform_set_drvdata(struct platform_device *pdev);
extern const void *ldv_devres_of_device_get_match_data(const struct device *dev);
extern void ldv_devres_dev_set_drvdata(struct device *dev, void *data);

extern void *__ldv_devm_drm_dev_alloc(struct device *parent, struct drm_driver *driver, size_t size, size_t offset);

extern int ldv_drmm_mode_config_init(struct drm_device *dev);
extern void ldv_drm_mode_config_cleanup(struct drm_device *dev);
extern void ldv_drm_crtc_cleanup(struct drm_crtc *crtc);
extern int ldv_drm_crtc_init_with_planes(struct drm_device *dev, struct drm_crtc *crtc, const struct drm_crtc_funcs *funcs);
extern void ldv_drm_plane_cleanup(struct drm_plane *plane);
extern int ldv_drm_universal_plane_init(struct drm_device *dev, struct drm_plane *plane, const struct drm_plane_funcs *funcs);
extern void ldv_drm_encoder_cleanup(struct drm_encoder *encoder);
extern int ldv_drm_encoder_init(struct drm_device *dev, struct drm_encoder *encoder, const struct drm_encoder_funcs *funcs);
extern int ldv_drm_simple_encoder_init(struct drm_device *dev, struct drm_encoder *encoder);

extern int ldv_dev_err_probe(int err);
#endif /* __LDV_LINUX_COLOR_MEMORY_H */
