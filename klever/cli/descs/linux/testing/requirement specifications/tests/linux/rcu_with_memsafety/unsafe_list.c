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
#include <linux/rculist.h>

struct local_str {
	int x;
	struct rcu_head rcu;
	struct hlist_node node;
};

static void local_str_reclaim(struct rcu_head *head)
{
	struct local_str *old = container_of(head, struct local_str, rcu);
	ldv_free(old);
}

static int __init ldv_init(void)
{
	int x = ldv_undef_int();
	struct local_str *local_ptr;
	struct local_str *local_ptr_2;
	struct hlist_head local_head;

	local_ptr = ldv_malloc(sizeof(*local_ptr));
    if (!local_ptr){
        return -1;
	}
    local_ptr->x = x;
	local_ptr->node.next = NULL;
	local_head.first = &(local_ptr->node);
	local_ptr->node.pprev = &(local_head.first);

	local_ptr_2 = ldv_malloc(sizeof(*local_ptr_2));
    if (!local_ptr_2){
		ldv_free(local_ptr);
        return -1;
	}
	local_ptr_2->x = ldv_undef_int();
	local_ptr_2->node.next = NULL;
	local_ptr_2->node.pprev = &(local_ptr->node.next);
	local_ptr->node.next = &(local_ptr_2->node);

	hlist_for_each_entry_rcu(local_ptr, &local_head, node) {
		call_rcu(&local_ptr->rcu, local_str_reclaim);
	}

	return 0;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
