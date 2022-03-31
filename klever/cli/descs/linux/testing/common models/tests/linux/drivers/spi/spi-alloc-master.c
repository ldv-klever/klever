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
#include <linux/device.h>
#include <linux/spi/spi.h>
#include <ldv/common/test.h>

static int __init ldv_init(void)
{
	struct device *host1 = ldv_undef_ptr_non_null(), *host2 = ldv_undef_ptr_non_null();
	unsigned int size1 = ldv_undef_uint(), size2 = ldv_undef_uint();
	struct spi_master *master1, *master2;

	master1 = spi_alloc_master(host1, size1);
	master2 = spi_alloc_master(host2, size2);

	if (!master1 && master2 && dev_get_drvdata(&master2->dev) == &master2[1])
		ldv_expected_error();

	return 0;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
