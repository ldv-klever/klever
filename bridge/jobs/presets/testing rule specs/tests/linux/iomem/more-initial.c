#include <linux/module.h>
#include <asm/io.h>

int __init my_init(void)
{
	void *res;
	phys_addr_t paddr;
	unsigned long size;

	res = ioremap(paddr, size);

	return 0;
}

module_init(my_init);
