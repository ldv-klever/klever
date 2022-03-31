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

#include <linux/module.h>
#include <linux/i2c.h>
#include <ldv/common/test.h>

static int __init ldv_init(void)
{
	struct i2c_client *client = ldv_undef_ptr_non_null();
	u8 smbus_cmd = ldv_undef_int_positive();
	u8 values[I2C_SMBUS_BLOCK_MAX + 1];
	ssize_t ret;

	ret = i2c_smbus_read_block_data(client, smbus_cmd, values);

	if (ret < 0)
		return ret;

	if (ret > I2C_SMBUS_BLOCK_MAX)
		ldv_unexpected_error();

	return 0;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
