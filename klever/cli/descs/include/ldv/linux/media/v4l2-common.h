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

#ifndef __LDV_LINUX_V4L2_COMMON_H
#define __LDV_LINUX_V4L2_COMMON_H

struct v4l2_subdev;
struct i2c_client;
struct v4l2_subdev_ops;
extern void ldv_v4l2_i2c_subdev_init(struct v4l2_subdev *sd, struct i2c_client *client, const struct v4l2_subdev_ops *ops);

#endif /* __LDV_LINUX_V4L2_COMMON_H */
