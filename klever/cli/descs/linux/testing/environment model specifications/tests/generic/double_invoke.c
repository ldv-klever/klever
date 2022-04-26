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

int cnt1 = 0;
int cnt2 = 0;

void ldv_handler1(struct ldv_resource *arg)
{
	cnt1++;
	if (cnt1 > 0 && cnt2 > 0)
		ldv_invoke_reached();
}

void ldv_handler2(struct ldv_resource *arg)
{
	cnt2++;
	if (cnt1 > 0 && cnt2 > 0)
		ldv_invoke_reached();
}


static struct ldv_driver ops1 = {
	.handler = & ldv_handler1,
};

static struct ldv_driver ops2 = {
	.handler = & ldv_handler2,
};

static int __init ldv_init(void)
{
	int res1;
	int res2;
	ldv_invoke_test();
	res1 = ldv_driver_register(& ops1);
	res2 = ldv_driver_register(& ops2);
	if (!res1 && !res2) {
		return 0;
	}
	if (!res1 && res2) {
		ldv_driver_deregister(& ops1);
		return res2;
	}
	if (res1 && !res2) {
		ldv_driver_deregister(& ops2);
		return res1;
	}
	if (res1 && res2) {
		ldv_driver_deregister(& ops1);
		ldv_driver_deregister(& ops2);
		return res1;
	}
}

static void __exit ldv_exit(void)
{
	ldv_driver_deregister(& ops1);
	ldv_driver_deregister(& ops1);
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
