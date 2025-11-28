/*
 * Copyright (c) 2025 ISP RAS (http://www.ispras.ru)
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
#include <ldv/common/test.h>
#include <linux/rcupdate.h>
#include <linux/rcutree.h>

struct local_str {
	int x;
	struct rcu_head rcu;
};

static int __init ldv_init(void)
{
	int x, y;
	struct local_str *local_ptr;
	x = ldv_undef_int();

	local_ptr = ldv_malloc(sizeof(*local_ptr));
    if (!local_ptr)
        return -1;

	rcu_read_lock();
	local_ptr->x = x;			//safe
	rcu_read_unlock();

	kfree_rcu(local_ptr, rcu);
	y = local_ptr->x;			//unsafe

	return 0;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
