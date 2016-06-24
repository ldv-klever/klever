#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/slab.h>
#include <linux/gfp.h>

static struct my_struct
{
	const char *name;
	unsigned int *irq;
};

static int __init my_init(void)
{
	struct my_struct *mem_1 = kmalloc(sizeof(struct my_struct), GFP_ATOMIC);
	return 0;
}

module_init(my_init);
