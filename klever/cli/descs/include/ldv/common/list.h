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

#ifndef __LDV_LIST_H
#define __LDV_LIST_H

struct ldv_list_node {
	void *data;
	struct ldv_list_node *next;
};

extern struct ldv_list_node *ldv_create_list_node(void *data);
extern struct ldv_list_node *ldv_insert_list_node(struct ldv_list_node *list_node, void *data);
extern void ldv_save_allocated_memory_to_list(void *ptr);

#endif /* __LDV_LIST_H */
