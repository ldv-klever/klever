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
#include <linux/interrupt.h>
#include <linux/irqreturn.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

unsigned int irq_id = 100;
void __percpu *percpu_dev_id;
int flip_a_coin;

static irqreturn_t irq_handler(int irq_id, void * data){
	ldv_invoke_callback();
	return IRQ_HANDLED;
}

static int __init ldv_init(void)
{
	int ret = ldv_undef_int();
	flip_a_coin = ldv_undef_int();
	if (flip_a_coin) {
		ldv_register();
		ret = request_percpu_irq(irq_id, irq_handler, "ldv_dev", percpu_dev_id);
		if (ret)
			ldv_deregister();
	}
	return ret;
}

static void __exit ldv_exit(void)
{
	if (flip_a_coin) {
		free_percpu_irq(irq_id, percpu_dev_id);
		ldv_deregister();
	}
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
