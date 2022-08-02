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

#ifndef __LDV_LINUX_DEVICE_H
#define __LDV_LINUX_DEVICE_H

#include <linux/types.h>

struct device;

extern void *ldv_dev_get_drvdata(const struct device *dev);
extern int ldv_dev_set_drvdata(struct device *dev, void *data);

extern void *ldv_devm_kmalloc(size_t size, gfp_t gfp);
extern void *ldv_devm_kzalloc(size_t size, gfp_t gfp);
extern void *ldv_devm_kmalloc_array(size_t n, size_t size, gfp_t gfp);
extern void *ldv_devm_kcalloc(size_t n, size_t size, gfp_t gfp);
extern void ldv_devm_kfree(const void *p);

#endif /* __LDV_LINUX_DEVICE_H */
