/*
 * Copyright (c) 2021 ISP RAS (http://www.ispras.ru)
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
#include <linux/slab.h>

static int __init ldv_init(void)
{
	unsigned char *var;
	int *nptr = NULL;

	var = kmalloc(50, GFP_KERNEL);
	if (!var)
		return 1;

	memset(var, 0xFF, 50);

	if (var[0] != 0xFF)
		*nptr = 1;

	if (var[1] != 0xFF)
		*nptr = 1;

	if (var[2] != 0xFF)
		*nptr = 1;

	if (var[4] != 0xFF)
		*nptr = 1;

	if (var[8] != 0xFF)
		*nptr = 1;

	if (var[16] != 0xFF)
		*nptr = 1;

	if (var[32] != 0xFF)
		*nptr = 1;

	kfree(var);

	return 0;
}

module_init(ldv_init);
