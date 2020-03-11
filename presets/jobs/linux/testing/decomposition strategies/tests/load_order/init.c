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
#include <ldv/test.h>

static int i;

void load_order_set_i(void) 
{
	i = 7;
}
EXPORT_SYMBOL(load_order_set_i);

static int __init init1(void)
{
	i = 5;
	return 0;
}

static void __exit exit1(void)
{
	if (i != 5)
		ldv_expected_error();
}

module_init(init1);
module_exit(exit1);
