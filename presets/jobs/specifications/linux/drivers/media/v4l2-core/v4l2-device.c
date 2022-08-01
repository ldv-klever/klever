/*
 * Copyright (c) 2022 ISP RAS (http://www.ispras.ru)
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

#include <media/v4l2-common.h>
#include <media/v4l2-device.h>
#include <ldv/linux/media/v4l2-device.h>
#include <ldv/linux/device.h>

int ldv_v4l2_device_register(struct device *dev, struct v4l2_device *v4l2_dev)
{
	if (v4l2_dev == NULL)
		return -EINVAL;

	if (dev == NULL) {
		if (!v4l2_dev->name[0])
			return -EINVAL;
		return 0;
	}

	v4l2_dev->dev = dev;

	/* See notes for presets/jobs/specifications/linux/drivers/spi.c. */
	ldv_dev_set_drvdata(dev, v4l2_dev);
	dev_set_drvdata(dev, v4l2_dev);

	return 0;
}

void ldv_v4l2_device_unregister(struct v4l2_device *v4l2_dev)
{
	if (v4l2_dev == NULL || !v4l2_dev->name[0])
		return;

	v4l2_dev->name[0] = '\0';
}
