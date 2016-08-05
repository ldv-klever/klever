#include <linux/module.h>
#include <linux/idr.h>

int __init my_init(void)
{
	struct idr *idp;

	idr_init(idp);

	return 0;
}

module_init(my_init);
