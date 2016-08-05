#include <linux/module.h>
#include <linux/idr.h>

int __init my_init(void)
{
	struct idr *idp;
	void *ptr, *found;
	int start, end;
	gfp_t gfp_mask;

	idr_init(idp);
	idr_destroy(idp);
	idr_alloc(idp, ptr, start, end, gfp_mask);

	return 0;
}

module_init(my_init);
