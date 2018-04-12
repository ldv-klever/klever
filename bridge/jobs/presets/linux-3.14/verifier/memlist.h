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