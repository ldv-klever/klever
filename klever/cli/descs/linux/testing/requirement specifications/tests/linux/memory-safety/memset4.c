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

struct A {
	unsigned char x;
	unsigned int y;
	unsigned long z;
};

static int __init ldv_init(void)
{
	struct A *var;
	int *nptr = NULL;

	var = kzalloc(sizeof(struct A) * sizeof(char), GFP_KERNEL);
	if (!var)
		return 1;

	memset(var, 0xFF, sizeof(struct A));

	if (var->x == 0)
		*nptr = 1;

	if (var->y == 0)
		*nptr = 1;

	if (var->z == 0)
		*nptr = 1;

	if (var->x != 255)
		*nptr = 1;

	if (var->y != 4294967295)
		*nptr = 1;

	if (var->z != 18446744073709551615UL)
		*nptr = 1;

	kfree(var);

	return 0;
}

module_init(ldv_init);
