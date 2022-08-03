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

#include <linux/module.h>
#include <linux/pci.h>
#include <media/v4l2-common.h>
#include <media/v4l2-device.h>
#include <ldv/common/test.h>

struct ldv_dev
{
	struct v4l2_device v4l2_dev;
};

static struct pci_dev ldv_pdev;
static struct ldv_dev ldv_dev;

static int __init ldv_init(void)
{
	int ret;

	ret = v4l2_device_register(&ldv_pdev.dev, &ldv_dev.v4l2_dev);
	if (ret)
		return ret;

	if (ldv_dev.v4l2_dev.dev != &ldv_pdev.dev)
		ldv_unexpected_error();

	if (&ldv_dev.v4l2_dev != pci_get_drvdata(&ldv_pdev))
		ldv_unexpected_error();

	v4l2_device_unregister(&ldv_dev.v4l2_dev);

	return 0;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
