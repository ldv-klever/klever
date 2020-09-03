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

#include <ldv/common/list.h>
#include <ldv/verifier/memory.h>

struct ldv_list_node *ldv_create_list_node(void *data)
{
	struct ldv_list_node *list_node;

	list_node = ldv_xzalloc(sizeof(*list_node));
	list_node->data = data;

	return list_node;
}

struct ldv_list_node *ldv_insert_list_node(struct ldv_list_node *list_node, void *data)
{
	struct ldv_list_node *new_list_node, *next_list_node;

	new_list_node = ldv_create_list_node(data);

	/* Insert new list node after first element of non-empty list. */
	if (list_node) {
		next_list_node = list_node->next;
		list_node->next = new_list_node;
		new_list_node->next = next_list_node;
	}

	return new_list_node;
}

static struct ldv_list_node ldv_allocated_memory_list;

void ldv_save_allocated_memory_to_list(void *ptr)
{
	if (!ptr)
		return;

	if (!ldv_allocated_memory_list.data)
		ldv_allocated_memory_list.data = ptr;
	else
		ldv_insert_list_node(&ldv_allocated_memory_list, ptr);
}
