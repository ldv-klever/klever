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

#include <linux/module.h>
#include <ldv/common/test.h>
#include <drm/drm_drv.h>
#include <drm/drm_managed.h>
#include <drm/drm_mode_config.h>
#include <drm/drm_plane.h>
#include <drm/drm_crtc.h>
#include <drm/drm_encoder.h>
#include <linux/platform_device.h>
#include <linux/device.h>
#include <ldv/linux/err.h>

struct local_device{
	u32 error_status;
};

static struct drm_driver drv_driver = {
	.name = "local_drv_driver",
};

static const struct drm_plane_funcs local_plane_funcs = {
	.destroy = drm_plane_cleanup,
};

static const struct drm_crtc_funcs local_crtc_funcs = {
	.destroy = drm_crtc_cleanup,
};

static const struct drm_encoder_funcs local_encoder_funcs = {
	.destroy = drm_encoder_cleanup,
};

static int __init ldv_init(void)
{
	struct platform_device *pdev;
	struct local_device *ldev;
	struct drm_device *drm;
	struct device *dev;
	struct device *master;
	int ret;


	pdev = ldv_malloc(sizeof(*pdev));
	if (!pdev){
        return -1;
	}
	dev = &pdev->dev;
	dev->driver_data = NULL;
	dev->devres_head.next = &dev->devres_head;

	master = ldv_malloc(sizeof(*master));
	if (!master){
        goto err_after_pdev;
	}

	drm = drm_dev_alloc(&drv_driver, master);
	if (ldv_is_err(drm)){
		goto err_after_master;
	}
	dev_set_drvdata(master, drm);

	ldev = devm_kzalloc(dev, sizeof(*ldev), GFP_KERNEL);
	if (!ldev){
		goto err_after_drm;
	}

	drm->dev_private = (void *)ldev;

	ret = drmm_mode_config_init(drm);
	if (ret){
		goto err_after_drm;
	}


// destroying
	if(dev->driver_data) drm_dev_put(drm);
	ldv_devres_release_all(dev);
	ldv_free(master);
	ldv_free(pdev);

	return 0;

err_after_drm:
	drm_dev_put(drm);

err_after_master:
	ldv_free(master);

err_after_pdev:
	ldv_devres_release_all(dev);
	ldv_free(pdev);

	return -1;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
