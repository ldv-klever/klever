/*
 * Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
 * Institute for System Programming of the Russian Academy of Sciences
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * ee the License for the specific language governing permissions and
 * limitations under the License.
 */

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

static void memory_allocation_1(void)
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
	struct page *mem_1 = alloc_pages(GFP_ATOMIC, order);
	struct page *mem_2 = alloc_pages_vma(GFP_ATOMIC, order, vma, addr, node);
	struct my_struct *mem_3 = kmalloc(sizeof(mem_3), GFP_ATOMIC);
	struct sk_buff *mem_4 = alloc_skb(sizeof(mem_3), GFP_ATOMIC);
	struct sk_buff *mem_5 = alloc_skb_fclone(sizeof(mem_3), GFP_ATOMIC);
	struct sk_buff *mem_6 = skb_copy(mem_5, GFP_ATOMIC);
	struct sk_buff *mem_7 = skb_share_check(mem_6, GFP_ATOMIC);
	struct sk_buff *mem_8 = skb_clone(mem_7, GFP_ATOMIC);
	struct sk_buff *mem_9 = skb_unshare(mem_8, GFP_ATOMIC);
	struct sk_buff *mem_10 = __netdev_alloc_skb(dev, length, GFP_ATOMIC);
	struct sk_buff *mem_11 = skb_copy_expand(mem_10, newheadroom, newtailroom, GFP_ATOMIC);
	struct my_struct *mem_12 = usb_alloc_coherent(dev_usb, sizeof(mem_3), GFP_ATOMIC, dma);
	struct urb *mem_13 =  usb_alloc_urb(iso_packets, GFP_ATOMIC);
	struct my_struct *mem_14 = kmalloc_node(sizeof(mem_3), GFP_ATOMIC, node);
	struct my_struct *mem_15 = kmem_cache_alloc(cache, GFP_ATOMIC);
	struct my_struct *mem_16 = mempool_alloc(pool, GFP_ATOMIC);
	struct my_struct *mem_17 = dma_pool_alloc(pool1, GFP_ATOMIC, dma);
	struct my_struct *mem_18 = kcalloc(length, sizeof(mem_3), GFP_ATOMIC);
	struct my_struct *mem_19 = krealloc(mem_18, sizeof(mem_3), GFP_ATOMIC);
	struct my_struct *mem_20 = dma_zalloc_coherent(device, sizeof(mem_3), dma, GFP_ATOMIC);
	struct my_struct *mem_21 = dma_alloc_coherent(device , sizeof(mem_3), dma, GFP_ATOMIC);

	// ALLOC with int
	int x_1 = __get_free_pages(GFP_ATOMIC, sizeof(mem_3));
	int x_2 = usb_submit_urb(mem_13, GFP_ATOMIC);
	int x_3 = mempool_resize(pool, order, GFP_ATOMIC);
	int x_4 = pskb_expand_head(mem_8, order, node, GFP_ATOMIC);

	// zalloc
	struct my_struct *mem_z1 = kzalloc(sizeof(mem_3), GFP_ATOMIC);
	struct my_struct *mem_z2 = kmem_cache_zalloc(cache, GFP_ATOMIC);
	struct my_struct *mem_z3 = kzalloc_node(sizeof(mem_3), GFP_ATOMIC, node);

	// macro
	struct page *mem_m1 = alloc_pages(GFP_ATOMIC, order);
	struct page *mem_m2 = alloc_page_vma(GFP_ATOMIC, vma, addr);
}

static void memory_allocation_2(void)
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
	struct page *mem_1 = alloc_pages(GFP_NOWAIT, order);
	struct page *mem_2 = alloc_pages_vma(GFP_NOWAIT, order, vma, addr, node);
	struct my_struct *mem_3 = kmalloc(sizeof(mem_3), GFP_NOWAIT);
	struct sk_buff *mem_4 = alloc_skb(sizeof(mem_3), GFP_NOWAIT);
	struct sk_buff *mem_5 = alloc_skb_fclone(sizeof(mem_3), GFP_NOWAIT);
	struct sk_buff *mem_6 = skb_copy(mem_5, GFP_NOWAIT);
	struct sk_buff *mem_7 = skb_share_check(mem_6, GFP_NOWAIT);
	struct sk_buff *mem_8 = skb_clone(mem_7, GFP_NOWAIT);
	struct sk_buff *mem_9 = skb_unshare(mem_8, GFP_NOWAIT);
	struct sk_buff *mem_10 = __netdev_alloc_skb(dev, length, GFP_NOWAIT);
	struct sk_buff *mem_11 = skb_copy_expand(mem_10, newheadroom, newtailroom, GFP_NOWAIT);
	struct my_struct *mem_12 = usb_alloc_coherent(dev_usb, sizeof(mem_3), GFP_NOWAIT, dma);
	struct urb *mem_13 =  usb_alloc_urb(iso_packets, GFP_NOWAIT);
	struct my_struct *mem_14 = kmalloc_node(sizeof(mem_3), GFP_NOWAIT, node);
	struct my_struct *mem_15 = kmem_cache_alloc(cache, GFP_NOWAIT);
	struct my_struct *mem_16 = mempool_alloc(pool, GFP_NOWAIT);
	struct my_struct *mem_17 = dma_pool_alloc(pool1, GFP_NOWAIT, dma);
	struct my_struct *mem_18 = kcalloc(length, sizeof(mem_3), GFP_NOWAIT);
	struct my_struct *mem_19 = krealloc(mem_18, sizeof(mem_3), GFP_NOWAIT);
	struct my_struct *mem_20 = dma_zalloc_coherent(device, sizeof(mem_3), dma, GFP_NOWAIT);
	struct my_struct *mem_21 = dma_alloc_coherent(device , sizeof(mem_3), dma, GFP_NOWAIT);
	usb_free_coherent(dev_usb, sizeof(mem_3), mem_12, 0);
	usb_free_urb(mem_13);

	// ALLOC with int
	int x_1 = __get_free_pages(GFP_NOWAIT, sizeof(mem_3));
	int x_2 = usb_submit_urb(mem_13, GFP_NOWAIT);
	int x_3 = mempool_resize(pool, order, GFP_NOWAIT);
	int x_4 = pskb_expand_head(mem_8, order, node, GFP_NOWAIT);

	// zalloc
	struct my_struct *mem_z1 = kzalloc(sizeof(mem_3), GFP_NOWAIT);
	struct my_struct *mem_z2 = kmem_cache_zalloc(cache, GFP_NOWAIT);
	struct my_struct *mem_z3 = kzalloc_node(sizeof(mem_3), GFP_NOWAIT, node);

	// macro
	struct page *mem_m1 = alloc_pages(GFP_NOWAIT, order);
	struct page *mem_m2 = alloc_page_vma(GFP_NOWAIT, vma, addr);
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

static int __init my_init(void)
{
	spinlock_t *lock;

	memory_allocation_1();
	memory_allocation_2();
	memory_allocation_nonatomic();

	spin_lock(lock);
	memory_allocation_1();
	memory_allocation_2();
	spin_unlock(lock);

	if (spin_trylock(lock)) {
		memory_allocation_1();
		memory_allocation_2();
		spin_unlock(lock);
	}
	memory_allocation_nonatomic();
	memory_allocation_1();
	memory_allocation_2();
	return 0;
}

module_init(my_init);
