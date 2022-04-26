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
#include <linux/firmware.h>
#include <ldv/common/test.h>

static int __init ldv_init(void)
{
	const struct firmware *fw;
	const char *fw_name = ldv_undef_ptr_non_null();
	struct device *dev = ldv_undef_ptr_non_null();
	int err;

	err = request_firmware(&fw, fw_name, dev);

	if (err)
	{
		if (fw)
			ldv_unexpected_error();

		return ldv_undef_int_negative();
	}

	if (!fw)
		ldv_unexpected_error();

	if (!fw->data)
		ldv_unexpected_error();

	release_firmware(fw);

	return 0;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
