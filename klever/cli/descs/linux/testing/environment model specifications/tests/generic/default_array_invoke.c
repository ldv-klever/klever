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
#include <ldv/verifier/nondet.h>
#include <ldv/linux/emg/test_model.h>
#include "ldvops.h"

int ldv_driver_array_register(struct ldv_driver **ops);
void ldv_driver_array_deregister(struct ldv_driver **ops);

void handler1(struct ldv_resource *arg)
{
	ldv_invoke_reached();
}

void handler2(struct ldv_resource *arg)
{
	ldv_invoke_reached();
}

static struct ldv_driver ops[2] = {
	{
		.handler = & handler1
	},
	{
		.handler = & handler2
	}
};

static int __init ldv_init(void)
{
	ldv_invoke_test();
	return ldv_driver_array_register(& ops);
}

static void __exit ldv_exit(void)
{
	ldv_driver_array_deregister(& ops);
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
