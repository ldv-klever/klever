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
#include <linux/hid.h>
#include <linux/input.h>
#include <ldv/common/test.h>

struct ldv_device
{
	struct hid_report *report;
};

static struct input_dev ldv_dev;

static int ldv_play(struct input_dev *dev, void *data, struct ff_effect *effect)
{
	return 0;
}

static int __init ldv_init(void)
{
	struct ldv_device *pldv_device;
	int ret;

	pldv_device = ldv_xmalloc(sizeof(*pldv_device));
	ret = input_ff_create_memless(&ldv_dev, pldv_device, ldv_play);
	if (ret)
	{
		ldv_free(pldv_device);
		return ret;
	}

	/* When input_ff_create_memless() finishes successfully, the kernel cares about releasing of memory pointed by the
	   second argument of input_ff_create_memless(). Probably, something should be invoked explicitly for that, say,
	   hid_hw_stop(), but it is another story. */

	return 0;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
