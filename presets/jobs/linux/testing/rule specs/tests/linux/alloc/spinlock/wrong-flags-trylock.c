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
#include <linux/spinlock.h>
#include <linux/slab.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

static DEFINE_SPINLOCK(ldv_lock);

static int __init ldv_init(void)
{
	unsigned long size = ldv_undef_ulong();
	void *data;

	ldv_assume(spin_trylock(&ldv_lock));
	data = kmalloc(size, GFP_KERNEL);
	ldv_assume(data != NULL);
	spin_unlock(&ldv_lock);

	kfree(data);

	return 0;
}

module_init(ldv_init);
