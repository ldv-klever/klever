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
#include <linux/kref.h>
#include <linux/slab.h>
#include <ldv/common/test.h>

struct ldv_struct {
	int x;
	struct kref kref;
	int y;
};

static int ldv_is_released = 0;

static void ldv_release(struct kref *kref)
{
	kfree(container_of(kref, struct ldv_struct, kref));
	ldv_is_released = 1;
}

static int __init ldv_init(void)
{
	struct ldv_struct *u;

	u = ldv_xzalloc(sizeof(*u));
	kref_init(&u->kref);
	kref_get(&u->kref);

	if (kref_put(&u->kref, ldv_release))
		ldv_unexpected_error();

	if (kref_put(&u->kref, ldv_release) != 1)
		ldv_unexpected_error();

	if (ldv_is_released != 1)
		ldv_unexpected_error();

	return 0;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
