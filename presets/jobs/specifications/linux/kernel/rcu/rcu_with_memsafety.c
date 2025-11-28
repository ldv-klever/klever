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

#include <linux/types.h>
#include <ldv/verifier/memory.h>
#include <net/net_namespace.h>

int ldv_rcu_counter = 0;
int ldv_rcu_callbacks_num = 0;
int ldv_kfree_rcu_callbacks_num = 0;
void *ldv_ptr;

// local struct with list of items to free (call_rcu)
struct rcu_head *old_rcu_heads;
// pointer to the item currently being freed (call_rcu)
struct rcu_head *curr_rcu_head;

// local struct with list of items to free (kfree_rcu)
struct rcu_head *old_kfree_rcu_heads;
// pointer to the item currently being freed (kfree_rcu)
struct rcu_head *curr_kfree_rcu_heads;

struct net *ldv_dnet;

void ldv_rcu_read_lock( void )
{
	ldv_rcu_counter += 1;
}

void ldv_rcu_read_unlock( void )
{
	ldv_rcu_counter -= 1;

	if ((ldv_rcu_callbacks_num > 0) && (ldv_rcu_counter == 0))
	{
		// callback
		while(old_rcu_heads != NULL) {
			curr_rcu_head = old_rcu_heads;
			old_rcu_heads = curr_rcu_head->next;
			(*curr_rcu_head->func)(curr_rcu_head);
		}
		ldv_rcu_callbacks_num = 0;
	}

	if ((ldv_kfree_rcu_callbacks_num > 0) && (ldv_rcu_counter == 0))
	{
		// callback
		while(old_kfree_rcu_heads != NULL) {
			curr_kfree_rcu_heads = old_kfree_rcu_heads;
			old_kfree_rcu_heads = curr_kfree_rcu_heads->next;
			ldv_free(curr_kfree_rcu_heads->func);
		}
		ldv_kfree_rcu_callbacks_num = 0;
	}
}

void ldv_call_rcu(struct rcu_head *head, rcu_callback_t func)
{
	if (ldv_rcu_counter)
	{
		if(ldv_rcu_callbacks_num == 0)
			old_rcu_heads = NULL;

		ldv_rcu_callbacks_num += 1;
		head->func = func;
		head->next = old_rcu_heads;
		old_rcu_heads = head;
	}
	else
	{
		// callback
		(*func)(head);
	}
}

void ldv_kvfree_call_rcu(struct rcu_head *head, rcu_callback_t func)
{
	if (head) {
		ldv_ptr = (void *) head - (unsigned long) func;
        if (ldv_rcu_counter)
        {
            if(ldv_kfree_rcu_callbacks_num == 0)
                old_kfree_rcu_heads = NULL;

            ldv_kfree_rcu_callbacks_num += 1;
            head->func = ldv_ptr;
            head->next = old_kfree_rcu_heads;
            old_kfree_rcu_heads = head;
        }
        else
        {
            // callback
            ldv_free(ldv_ptr);
        }
	}
}

int ldv_register_pernet_device(struct pernet_operations *ops) {
    ldv_dnet = external_allocated_data();
    return ops->init(ldv_dnet);
}

void ldv_unregister_pernet_device(struct pernet_operations *ops) {
    ops->exit(ldv_dnet);
}
