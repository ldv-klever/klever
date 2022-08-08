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
#include <linux/i2c.h>
#include <ldv/common/test.h>

enum ldv_chips { ldv_chip_1, ldv_chip_2, ldv_chip_3 };

static const struct i2c_device_id ldv_id[] = {
	{"ldv_chip_1", ldv_chip_1},
	{"ldv_chip_2", ldv_chip_2},
	{"ldv_chip_3", ldv_chip_3},
	{}
};

struct i2c_client ldv_client;

static int __init ldv_init(void)
{
	int id;

	id = i2c_match_id(ldv_id, &ldv_client)->driver_data;

	if (id < ldv_chip_1 || id > ldv_chip_3)
		ldv_unexpected_memory_safety_error();

	return 0;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
