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


static struct my_struct
{
	const char *name;
	unsigned int *irq;
};

static void memory_allocation(gfp_t flags)
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

	// ALLOC
	struct page *mem_1 = alloc_pages(flags, order);
	struct page *mem_2 = alloc_pages_vma(flags, order, vma, addr, node);
	struct my_struct *mem_3 = kmalloc(sizeof(mem_3), flags);
	struct sk_buff *mem_4 = alloc_skb(sizeof(mem_3), flags);
	struct sk_buff *mem_5 = alloc_skb_fclone(sizeof(mem_3), flags);
	struct sk_buff *mem_6 = skb_copy(mem_5, flags);
	struct sk_buff *mem_7 = skb_share_check(mem_6, flags);
	struct sk_buff *mem_8 = skb_clone(mem_7, flags);
	struct sk_buff *mem_9 = skb_unshare(mem_8, flags);
	struct sk_buff *mem_10 = __netdev_alloc_skb(dev, length, flags);
	struct sk_buff *mem_11 = skb_copy_expand(mem_10, newheadroom, newtailroom, flags);
	struct my_struct *mem_12 = usb_alloc_coherent(dev_usb, sizeof(mem_3), flags, dma);
	struct urb *mem_13 =  usb_alloc_urb(iso_packets, flags);
	struct my_struct *mem_14 = kmalloc_node(sizeof(mem_3), flags, node);
	struct my_struct *mem_15 = kmem_cache_alloc(cache, flags);
	struct my_struct *mem_16 = mempool_alloc(pool, flags);
	struct my_struct *mem_17 = dma_pool_alloc(pool1, flags, dma);
	struct my_struct *mem_18 = kcalloc(length, sizeof(mem_3), flags);
	struct my_struct *mem_19 = krealloc(mem_18, sizeof(mem_3), flags);
	struct my_struct *mem_20 = dma_zalloc_coherent(device, sizeof(mem_3), dma, flags);
	struct my_struct *mem_21 = dma_alloc_coherent(device , sizeof(mem_3), dma, flags);

	// ALLOC with int
	int x_1 = __get_free_pages(flags, sizeof(mem_3));
	int x_2 = usb_submit_urb(mem_13, flags);
	int x_3 = mempool_resize(pool, order, flags);
	int x_4 = pskb_expand_head(mem_8, order, node, flags);

	// zalloc
	struct my_struct *mem_z1 = kzalloc(sizeof(mem_3), flags);
	struct my_struct *mem_z2 = kmem_cache_zalloc(cache, flags);
	struct my_struct *mem_z3 = kzalloc_node(sizeof(mem_3), flags, node);

	// macro
	struct page *mem_m1 = alloc_pages(flags, order);
	struct page *mem_m2 = alloc_page_vma(flags, vma, addr);
}

static void memory_allocation_nonatomic(void)
{
	int size, node;
	void *mem_1 = vmalloc(size);
	void *mem_2 = vzalloc(size);
	void *mem_3 = vmalloc_user(size);
	void *mem_4 = vmalloc_node(size, node);
	void *mem_5 = vzalloc_node(size, node);
	void *mem_6 = vmalloc_exec(size);
	void *mem_7 = vmalloc_32(size);
	void *mem_8 = vmalloc_32_user(size);
}

static irqreturn_t my_func_irq(int irq, void *dev_id)
{
	memory_allocation(GFP_ATOMIC);
	return IRQ_HANDLED;
}

static int __init my_init(void)
{
	gfp_t flags;
	unsigned int irq;
	const char *name;
	void *dev;
	memory_allocation(flags);
	memory_allocation_nonatomic();
	memory_allocation(flags);
	request_irq(irq, my_func_irq, IRQF_SHARED, name, dev);
	memory_allocation(flags);
	memory_allocation_nonatomic();
	memory_allocation(flags);
	return 0;
}

module_init(my_init);
