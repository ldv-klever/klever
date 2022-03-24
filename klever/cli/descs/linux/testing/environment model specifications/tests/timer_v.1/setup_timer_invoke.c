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
#include <linux/timer.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

int flip_a_coin;
struct timer_list ldv_timer;
unsigned long data;

void ldv_handler(unsigned long data)
{
	ldv_invoke_reached();
}

static int __init ldv_init(void)
{
    int ret;
	ldv_invoke_test();
	setup_timer(&ldv_timer, ldv_handler, data);
	ret = mod_timer(&ldv_timer, jiffies + msecs_to_jiffies(200));
	if (ret)
	    return 0;
	else
	    return -1;
}

static void __exit ldv_exit(void)
{
	del_timer(&ldv_timer);
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
