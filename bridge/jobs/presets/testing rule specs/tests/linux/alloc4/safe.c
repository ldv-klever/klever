#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/slab.h>
#include <linux/etherdevice.h>
#include <linux/gfp.h>

static struct my_struct
{
	const char *name;
	unsigned int *irq;
};

static int __init my_init(void)
{
	int sizeof_priv, length;
	unsigned int txqs, rxqs;
	struct my_struct *mem_1 = kmalloc(sizeof(struct my_struct), GFP_ATOMIC);
	struct my_struct *mem_2 = kcalloc(length, sizeof(struct my_struct), GFP_ATOMIC);
	struct net_device *mem_3 = alloc_etherdev_mqs(sizeof_priv, txqs, rxqs);
	if (!IS_ERR_OR_NULL(mem_1))
		kfree(mem_1);
	if (!IS_ERR_OR_NULL(mem_2))
		kfree(mem_2);
	if (!IS_ERR_OR_NULL(mem_3))
		kfree(mem_3);
	return 0;
}

module_init(my_init);
