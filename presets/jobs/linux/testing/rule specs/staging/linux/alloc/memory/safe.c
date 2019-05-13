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
#include <linux/slab.h>
#include <linux/gfp.h>
#include <linux/etherdevice.h>
#include <verifier/nondet.h>
#include "memory.h"

static int __init ldv_init(void)
{
	size_t n = ldv_undef_uint();
	int sizeof_priv = ldv_undef_int();
	unsigned int txqs = ldv_undef_uint(), rxqs = ldv_undef_uint();
	struct ldv_struct *ldv1, *ldv2, *ldv3;

	ldv1 = kmalloc(sizeof(struct ldv_struct), GFP_ATOMIC);
	ldv_assume(ldv1);
	kfree(ldv1);

	ldv2 = kcalloc(n, sizeof(struct ldv_struct), GFP_ATOMIC);
	ldv_assume(ldv2);
	kfree(ldv2);

	ldv3 = alloc_etherdev_mqs(sizeof_priv, txqs, rxqs);
	ldv_assume(ldv3);
	kfree(ldv3);

	return 0;
}

module_init(ldv_init);
