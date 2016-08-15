#include <linux/module.h>
#include <asm-generic/bitops/find.h>

int __init my_init(void)
{
	unsigned long size, offset, res;
	const unsigned long *addr;
	res = find_next_zero_bit(addr, size, offset);
	
	return 0;
}

module_init(my_init);
