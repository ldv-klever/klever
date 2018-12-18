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
#include <linux/slab.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

static irqreturn_t ldv_handler(int irq, void *dev_id)
{
	size_t size = ldv_undef_uint();
	void *data;

	data = kmalloc(size, GFP_KERNEL);
	ldv_assume(data != NULL);
	kfree(data);

	return IRQ_HANDLED;
}

static int __init ldv_init(void)
{
	unsigned int irq = ldv_undef_uint();
	unsigned long flags = ldv_undef_ulong();
	const char *name = ldv_undef_ptr();
	void *dev = ldv_undef_ptr();

	ldv_assume(request_irq(irq, ldv_handler, flags, name, dev));

	return 0;
}

module_init(ldv_init);
