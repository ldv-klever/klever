/*
 * Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
 * Institute for System Programming of the Russian Academy of Sciences
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
 * ee the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <linux/module.h>
#include <linux/workqueue.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

int flip_a_coin;
static struct work_struct work;

static void ldv_handler(struct work_struct *work)
{
	ldv_invoke_callback();
}

static int __init ldv_init(void)
{
	int cpu = 1;

	flip_a_coin = ldv_undef_int();
	if (flip_a_coin) {
		INIT_WORK(&work, ldv_handler);
		ldv_register();
		schedule_work_on(cpu, &work);
	}
	return 0;
}

static void __exit ldv_exit(void)
{
	if (flip_a_coin) {
		cancel_work_sync(&work);
		ldv_deregister();
	}
}

module_init(ldv_init);
module_exit(ldv_exit);
