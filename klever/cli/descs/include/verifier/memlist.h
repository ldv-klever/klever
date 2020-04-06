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

#include <verifier/memory.h>

struct ldv_list_element
{
	void *data;
	struct ldv_list_element *next;
};

typedef struct ldv_list_element *ldv_list_ptr;

struct ldv_list_element global_list = {
    .data = NULL,
    .next = NULL
};

static inline ldv_list_ptr ldv_list_create(void *data)
{
	ldv_list_ptr list = NULL;

	list = ldv_xmalloc(sizeof(*list));

	list->data = data;
	list->next = NULL;

	return list;
}

static inline void ldv_save_pointer(void *data)
{
    ldv_list_ptr element;
    ldv_list_ptr cached;

    if (global_list.data == NULL) {
        element = & global_list;
        element->data = data;
    } else {
        element = ldv_list_create(data);
        cached = global_list.next;
        global_list.next = element;
        element->next = cached;
    }

	return;
}