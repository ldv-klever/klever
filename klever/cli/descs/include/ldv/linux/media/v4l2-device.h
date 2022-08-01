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

#ifndef __LDV_LINUX_MEDIA_V4L2_DEVICE_H
#define __LDV_LINUX_MEDIA_V4L2_DEVICE_H

struct dev;
struct v4l2_device;

extern int ldv_v4l2_device_register(struct device *dev, struct v4l2_device *v4l2_dev);
extern void ldv_v4l2_device_unregister(struct v4l2_device *v4l2_dev);

#endif /* __LDV_LINUX_MEDIA_V4L2_DEVICE_H */
