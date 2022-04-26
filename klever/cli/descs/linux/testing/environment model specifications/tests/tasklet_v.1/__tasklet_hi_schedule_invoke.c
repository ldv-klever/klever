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
#include <linux/interrupt.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

unsigned long data;
static struct tasklet_struct ldv_tasklet;

static void ldv_handler(unsigned long data)
{
	ldv_invoke_reached();
}

static int __init ldv_init(void)
{
	ldv_invoke_test();
	data = ldv_undef_ulong();
	tasklet_init(&ldv_tasklet, ldv_handler, data);
	tasklet_hi_schedule(&ldv_tasklet);
	return 0;
}

static void __exit ldv_exit(void)
{
	tasklet_kill(&ldv_tasklet);
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");