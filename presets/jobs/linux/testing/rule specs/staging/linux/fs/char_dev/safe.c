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

#include <linux/module.h>
#include <linux/fs.h>

static int __init ldv_init(void)
{
	dev_t *dev;
	const struct file_operations *fops;
	unsigned int baseminor, count;

	if (!alloc_chrdev_region(dev, baseminor, count, "test__")) {
		unregister_chrdev_region(dev, count);
	}

	if (!register_chrdev_region(dev, count, "__test")) {
		unregister_chrdev_region(dev, count);
	}

	if (!register_chrdev(2, "test", fops)) {
		unregister_chrdev_region(dev, count);
	}

	if (register_chrdev(0, "test", fops) > 0) {
		unregister_chrdev_region(dev, count);
	}

	return 0;
}

module_init(ldv_init);
