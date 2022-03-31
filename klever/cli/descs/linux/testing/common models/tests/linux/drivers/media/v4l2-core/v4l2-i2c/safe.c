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

#include <linux/module.h>
#include <linux/i2c.h>
#include <media/v4l2-common.h>
#include <media/v4l2-device.h>
#include <ldv/common/test.h>


static int __init ldv_init(void)
{
	struct v4l2_subdev sd;
	struct i2c_client client;
	struct v4l2_subdev_ops ldv_ops;

	v4l2_i2c_subdev_init(&sd, &client, &ldv_ops);

	if (sd.ops != &ldv_ops)
		ldv_unexpected_error();

	if (&client != v4l2_get_subdevdata(&sd))
		ldv_unexpected_error();

	if (&sd != i2c_get_clientdata(&client))
		ldv_unexpected_error();

	return 0;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
