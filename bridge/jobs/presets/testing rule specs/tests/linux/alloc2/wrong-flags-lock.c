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
	int order, node, newtailroom, newheadroom, iso_packets;
	struct vm_area_struct *vma;
	unsigned long addr;
	bool hugepage;
	unsigned int length;
	struct net_device *dev;
	struct usb_device *dev_usb;
	dma_addr_t *dma;
	struct kmem_cache * cache;
	mempool_t *pool;
	struct dma_pool *pool1;
	struct device *device;
	gfp_t flags;

	struct page *mem_1;
	struct page *mem_2;
	struct my_struct *mem_3;
	struct sk_buff *mem_4;
	struct sk_buff *mem_5;
	struct sk_buff *mem_6;
	struct sk_buff *mem_7;
	struct sk_buff *mem_8;
	struct sk_buff *mem_9;
	struct sk_buff *mem_10;
	struct sk_buff *mem_11;
	struct my_struct *mem_12;
	struct urb *mem_13;
	struct my_struct *mem_14;
	struct my_struct *mem_15;
	struct my_struct *mem_16;
	struct my_struct *mem_17;
	struct my_struct *mem_18;
	struct my_struct *mem_19;
	struct my_struct *mem_20;
	struct my_struct *mem_21;
	int x_1, x_2, x_3, x_4;
	void *mem_z1, *mem_z2, *mem_z3;
	struct page *mem_m1;
	struct page *mem_m2;

	if (undef_int()) mem_1 = alloc_pages(flags, order);
	if (undef_int()) mem_2 = alloc_pages_vma(flags, order, vma, addr, node);
	if (undef_int()) mem_3 = kmalloc(sizeof(mem_3), flags);
	if (undef_int()) mem_4 = alloc_skb(sizeof(mem_3), flags);
	if (undef_int()) mem_5 = alloc_skb_fclone(sizeof(mem_3), flags);
	if (undef_int()) mem_6 = skb_copy(mem_5, flags);
	if (undef_int()) mem_7 = skb_share_check(mem_6, flags);
	if (undef_int()) mem_8 = skb_clone(mem_7, flags);
	if (undef_int()) mem_9 = skb_unshare(mem_8, flags);
	if (undef_int()) mem_10 = __netdev_alloc_skb(dev, length, flags);
	if (undef_int()) mem_11 = skb_copy_expand(mem_10, newheadroom, newtailroom, flags);
	if (undef_int()) mem_12 = usb_alloc_coherent(dev_usb, sizeof(mem_3), flags, dma);
	if (undef_int()) mem_13 =  usb_alloc_urb(iso_packets, flags);
	if (undef_int()) mem_14 = kmalloc_node(sizeof(mem_3), flags, node);
	if (undef_int()) mem_15 = kmem_cache_alloc(cache, flags);
	if (undef_int()) mem_16 = mempool_alloc(pool, flags);
	if (undef_int()) mem_17 = dma_pool_alloc(pool1, flags, dma);
	if (undef_int()) mem_18 = kcalloc(length, sizeof(mem_3), flags);
	if (undef_int()) mem_19 = krealloc(mem_18, sizeof(mem_3), flags);
	if (undef_int()) mem_20 = dma_zalloc_coherent(device, sizeof(mem_3), dma, flags);
	if (undef_int()) mem_21 = dma_alloc_coherent(device , sizeof(mem_3), dma, flags);
	if (undef_int())  x_1 = __get_free_pages(flags, sizeof(mem_3));
	if (undef_int())  x_2 = usb_submit_urb(mem_13, flags);
	if (undef_int())  x_3 = mempool_resize(pool, order, flags);
	if (undef_int())  x_4 = pskb_expand_head(mem_8, order, node, flags);
	if (undef_int()) mem_z1 = kzalloc(sizeof(mem_3), flags);
	if (undef_int()) mem_z2 = kmem_cache_zalloc(cache, flags);
	if (undef_int()) mem_z3 = kzalloc_node(sizeof(mem_3), flags, node);
	if (undef_int()) mem_m1 = alloc_pages(flags, order);
	if (undef_int()) mem_m2 = alloc_page_vma(flags, vma, addr);
}

static int __init my_init(void)
{
	spinlock_t *lock;
	spin_lock(lock);
	memory_allocation();
	spin_unlock(lock);
	return 0;
}

module_init(my_init);
