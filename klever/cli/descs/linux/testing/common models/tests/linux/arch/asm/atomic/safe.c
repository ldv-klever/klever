/*
 * Copyright (c) 2020 ISP RAS (http://www.ispras.ru)
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
#include <ldv/test.h>

struct ldv_struct {
	int x;
	struct kref kref;
	int y;
};

static void ldv_release(struct kref *kref)
{
	kfree(container_of(kref, struct ldv_struct, kref));
}

static int __init ldv_init(void)
{
	/* TODO: this API was added just in Linux 4.11 while these test cases are for Linux 3.14.79.
	refcount_t r;

	refcount_set(&r, 1);

	if (refcount_read(&r) != 1)
		ldv_unexpected_error();

	refcount_inc(&r);
	if (refcount_read(&r) != 2)
		ldv_unexpected_error();

	refcount_inc(&r);
	if (refcount_read(&r) != 3)
		ldv_unexpected_error();

	refcount_dec(&r);
	if (refcount_read(&r) != 2)
		ldv_unexpected_error();

	refcount_dec(&r);
	if (refcount_read(&r) != 1)
		ldv_unexpected_error();
	*/
	atomic_t v;
	struct ldv_struct *u;

	atomic_set(&v, 1);
	if (atomic_read(&v) != 1)
		ldv_unexpected_error();
	atomic_add(3, &v);
	if (atomic_read(&v) != 4)
		ldv_unexpected_error();
	atomic_sub(2, &v);
	if (atomic_read(&v) != 2)
		ldv_unexpected_error();
	if (atomic_sub_and_test(1, &v))
		ldv_unexpected_error();
	if (!atomic_sub_and_test(1, &v))
		ldv_unexpected_error();
	atomic_inc(&v);
	if (atomic_read(&v) != 1)
		ldv_unexpected_error();
	atomic_dec(&v);
	if (atomic_read(&v))
		ldv_unexpected_error();
	atomic_set(&v, 2);
	if (atomic_dec_and_test(&v))
		ldv_unexpected_error();
	if (!atomic_dec_and_test(&v))
		ldv_unexpected_error();
	atomic_set(&v, -2);
	if (atomic_inc_and_test(&v))
		ldv_unexpected_error();
	if (!atomic_inc_and_test(&v))
		ldv_unexpected_error();
	if (atomic_add_return(3, &v) != 3)
		ldv_unexpected_error();
	if (atomic_add_negative(1, &v))
		ldv_unexpected_error();
	if (!atomic_add_negative(-5, &v))
		ldv_unexpected_error();
	/* TODO: these functions are not available in Linux 3.14.79.
	if (atomic_fetch_sub(-2, &v) != -1)
		ldv_unexpected_error();
	if (atomic_fetch_add(3, &v) != -3)
		ldv_unexpected_error();
	if (atomic_read(&v))
		ldv_unexpected_error();
	*/

	u = ldv_xzalloc(sizeof(*u));
	kref_init(&u->kref);
	kref_get(&u->kref);
	if (kref_put(&u->kref, ldv_release))
		ldv_unexpected_error();
	if (kref_put(&u->kref, ldv_release) != 1)
		ldv_unexpected_error();

	return 0;
}

module_init(ldv_init);
