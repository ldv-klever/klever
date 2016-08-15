#include <linux/module.h>
#include <linux/idr.h>

int __init my_init(void)
{
	struct idr *idp, *idp2;
	void *ptr, *found;
	int start, end;
	gfp_t gfp_mask;

	idr_init(idp);
	idr_init(idp2);
	idr_alloc(idp, ptr, start, end, gfp_mask);
	found = idr_find(idp, end);
	idr_remove(idp, end);
	idr_alloc(idp, ptr, start, end, gfp_mask);
	found = idr_find(idp, end);
	idr_remove(idp, end);
	idr_destroy(idp);

	idr_alloc(idp2, ptr, start, end, gfp_mask);
	found = idr_find(idp2, end);
	idr_remove(idp2, end);
	idr_alloc(idp2, ptr, start, end, gfp_mask);
	found = idr_find(idp2, end);
	idr_remove(idp2, end);
	idr_destroy(idp2);

	return 0;
}

module_init(my_init);
