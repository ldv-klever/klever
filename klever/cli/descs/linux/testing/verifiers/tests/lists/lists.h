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

#include <ldv/verifier/memory.h>

/*
 * List elements consist of two fields:
 * - pointer on abstract data,
 * - pointer on next list element.
 */
struct ldv_list_element
{
	void *data;
	struct ldv_list_element *next;
};

typedef struct ldv_list_element *ldv_list_ptr;

static inline ldv_list_ptr ldv_list_get_next(ldv_list_ptr list);
static inline ldv_list_ptr ldv_list_get_prev(ldv_list_ptr list_first,
					     ldv_list_ptr list);

static inline ldv_list_ptr ldv_list_create(void *data)
{
	ldv_list_ptr list = NULL;

	list = ldv_xmalloc(sizeof(*list));

	list->data = data;
	list->next = NULL;

	return list;
}


static inline ldv_list_ptr ldv_list_delete(ldv_list_ptr *list_first,
					   ldv_list_ptr list)
{
	ldv_list_ptr list_prev;

	/* Return NULL if deleting first element of list. */
	if (*list_first == list) {
		*list_first = ldv_list_get_next(list);
		ldv_free(list);

		return NULL;
	}
	/*
	 * Otherwise update next list element for the previous one and return
	 * it.
         */
	else {
		list_prev = ldv_list_get_prev(*list_first, list);
		list_prev->next = list->next;
		ldv_free(list);

		return list_prev;
	}
}

static inline void ldv_list_delete_all(ldv_list_ptr list)
{
	ldv_list_ptr list_cur = NULL, list_delete = NULL;

	for (list_cur = list_delete = list; list_cur; list_delete = list_cur) {
		list_cur = ldv_list_get_next(list_cur);
		ldv_free(list_delete);
	}
}

static inline void *ldv_list_get_data(ldv_list_ptr list)
{
	return list->data;
}

static inline ldv_list_ptr ldv_list_get_next(ldv_list_ptr list)
{
	return list->next;
}

static inline ldv_list_ptr ldv_list_get_last(ldv_list_ptr list)
{
	ldv_list_ptr list_cur = NULL;

	/* Walk to last list element and return it. */
	for (list_cur = list; list_cur->next; list_cur = ldv_list_get_next(list_cur)) ;

	return list_cur;
}

static inline ldv_list_ptr ldv_list_get_prev(ldv_list_ptr list_first,
					     ldv_list_ptr list)
{
	ldv_list_ptr list_cur = NULL;

	if (list_first == list)
		return list_first;

	for (list_cur = list_first; list_cur; list_cur = ldv_list_get_next(list_cur))
		if (ldv_list_get_next(list_cur) == list)
			return list_cur;

	return NULL;
}

static inline ldv_list_ptr ldv_list_insert_data(ldv_list_ptr list, void *data)
{
	ldv_list_ptr list_next = NULL, list_new = NULL;

	list_new = ldv_list_create(data);

	/* Insert new list element with given data to non-empty list. */
	if (list) {
		list_next = ldv_list_get_next(list);
		list->next = list_new;
		list_new->next = list_next;
	}

	return list_new;
}

static inline unsigned int ldv_list_len(ldv_list_ptr list)
{
	unsigned int list_len = 0;
	ldv_list_ptr list_cur;

	for (list_cur = list; list_cur; list_cur = ldv_list_get_next(list_cur), list_len++) ;

	return list_len;
}

static inline void ldv_list_set_data(ldv_list_ptr list, void *data)
{
	list->data = data;
}
