#include <linux/module.h>
#include <asm/io.h>

int __init my_init(void)
{
	void *res;
	phys_addr_t paddr;
	unsigned long size;

	iounmap(res);

	return 0;
}

module_init(my_init);
