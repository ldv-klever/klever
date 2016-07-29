#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/usb.h>
#include <linux/irq.h>
#include <linux/slab.h>
#include <linux/gfp.h>
#include <linux/skbuff.h>
#include <linux/slab.h>
#include <linux/mempool.h>
#include <linux/dmapool.h>
#include <linux/dma-mapping.h>
#include <linux/vmalloc.h>
#include <linux/spinlock.h>


static struct my_struct
{
	const char *name;
	unsigned int *irq;
};

static int undef_int(void)
{
	int nondet;
	return nondet;
}

static void memory_allocation(void)
{
	gfp_t flags;
	struct my_struct *mem = kmalloc(sizeof(mem), flags);
	kfree(mem);
}

static int __init my_init(void)
{
	spinlock_t *lock;
	if (spin_trylock(lock)) {
		memory_allocation();
		spin_unlock(lock);
	}
	return 0;
}

module_init(my_init);
