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

#include <linux/i2c.h>
#include <media/v4l2-common.h>
#include <media/v4l2-device.h>
#include <ldv/linux/media/v4l2-common.h>
#include <ldv/linux/device.h>

void ldv_v4l2_i2c_subdev_init(struct v4l2_subdev *sd, struct i2c_client *client, const struct v4l2_subdev_ops *ops)
{
	sd->ops = ops;
	v4l2_set_subdevdata(sd, client);
	/* See notes for presets/jobs/specifications/linux/drivers/spi.c. */
	ldv_dev_set_drvdata(&client->dev, sd);
	dev_set_drvdata(&client->dev, sd);
}
