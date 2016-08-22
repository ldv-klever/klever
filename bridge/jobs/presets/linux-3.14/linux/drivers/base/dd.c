/*
 * Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
 * Institute for System Programming of the Russian Academy of Sciences
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
 * ee the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <linux/device.h>
#include <verifier/memory.h>
#include <verifier/nondet.h>

struct device_private {
	void *driver_data;
};

void *ldv_dev_get_drvdata(const struct device *dev)
{
	if (dev && dev->p)
		return dev->p->driver_data;
	return 0;
}

int ldv_dev_set_drvdata(struct device *dev, void *data)
{
	int err = ldv_undef_int_nonpositive();

	if (!err) {
		dev->p = ldv_xzalloc(sizeof(*dev->p));
		dev->p->driver_data = data;
	}

	return err;
}
