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

#include <ldv/common/list.h>
#include <linux/device.h>
#include <linux/types.h>
#include <ldv/linux/device.h>
#include <ldv/verifier/memory.h>
#include <ldv/verifier/nondet.h>

/* This is a private structure that we can define anyhow. For us only field
   driver_data is important. You can see how it is used below. */
struct device_private {
	void *driver_data;
};

void *ldv_dev_get_drvdata(const struct device *dev)
{
	if (dev && dev->p)
		return dev->p->driver_data;

	return 0;
}

/* Do not return any error codes since callers usually don't check them. This
 * is the case for, say, Linux 3.14 while in, say, Linux 4.7 there is no need
 * in this model at all (and it will not be invoked - see aspect) since
 * dev_set_drvdata() is static inline function that always returns
 * successfully.
 */
int ldv_dev_set_drvdata(struct device *dev, void *data)
{
	dev->p = ldv_xzalloc(sizeof(*dev->p));
	ldv_save_allocated_memory_to_list(dev->p);
	dev->p->driver_data = data;

	return 0;
}
