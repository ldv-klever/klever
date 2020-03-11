/*
 * Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
 * Ivannikov Institute for System Programming of the Russian Academy of Sciences
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
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <linux/slab.h>
#include <linux/gfp.h>
#include <linux/skbuff.h>
#include <linux/mempool.h>
#include <linux/dmapool.h>
#include <linux/dma-mapping.h>
#include <linux/vmalloc.h>
#include <linux/usb.h>
#include <verifier/nondet.h>

static inline void ldv_alloc(gfp_t flags)
{
	size_t size1 = ldv_undef_uint();
	void *data1 = kmalloc(size1, flags);
	size_t n2 = ldv_undef_uint();
	size_t size2 = ldv_undef_uint();
	void *data2 = kcalloc(n2, size2, flags);
	const void *p3 = ldv_undef_ptr();
	size_t size3 = ldv_undef_uint();
	void *data3 = krealloc(p3, size3, flags);
	size_t size4 = ldv_undef_uint();
	void *data4 = kzalloc(size4, flags);
	size_t size5 = ldv_undef_uint();
	int node5 = ldv_undef_int();
	void *data5 = kmalloc_node(size5, flags, node5);
	size_t size6 = ldv_undef_uint();
	int node6 = ldv_undef_int();
	void *data6 = kzalloc_node(size6, flags, node6);
	struct kmem_cache *cachep7 = ldv_undef_ptr();
	void *data7 = kmem_cache_alloc(cachep7, flags);
	struct kmem_cache *cachep8 = ldv_undef_ptr();
	void *data8 = kmem_cache_zalloc(cachep8, flags);
	mempool_t *pool9 = ldv_undef_ptr();
	struct page *data9 = mempool_alloc(pool9, flags);
	int new_min_nr10 = ldv_undef_int();
	int data10 = mempool_resize(pool9, new_min_nr10, flags);
	int order11 = ldv_undef_int();
	struct page *data11 = alloc_pages(flags, order11);
	int order12 = ldv_undef_int();
	struct vm_area_struct *vma12 = ldv_undef_ptr();
	unsigned long addr12 = ldv_undef_ulong();
	int node12 = ldv_undef_int();
	struct page *data12 = alloc_pages_vma(flags, order12, vma12, addr12, node12);
	unsigned int order13 = ldv_undef_uint();
	unsigned long data13 = __get_free_pages(flags, order13);
	struct dma_pool *pool14 = ldv_undef_ptr();
	dma_addr_t *handle14 = ldv_undef_ptr();
	void *data14 = dma_pool_alloc(pool14, flags, handle14);
	struct device *dev15 = ldv_undef_ptr_non_null();
	size_t size15 = ldv_undef_uint();
	dma_addr_t *dma_handle15 = ldv_undef_ptr();
	void *data15 = dma_zalloc_coherent(dev15, size15, dma_handle15, flags);
	struct device *dev16 = ldv_undef_ptr_non_null();
	size_t size16 = ldv_undef_uint();
	dma_addr_t *dma_handle16 = ldv_undef_ptr();
	void *data16 = dma_alloc_coherent(dev16, size16, dma_handle16, flags);
	unsigned int size17 = ldv_undef_uint();
	struct sk_buff *data17 = alloc_skb(size17, flags);
	unsigned int size18 = ldv_undef_uint();
	struct sk_buff *data18 = alloc_skb_fclone(size18, flags);
	struct sk_buff *data19 = skb_copy(data18, flags);
	struct sk_buff *data20 = skb_share_check(data18, flags);
	struct sk_buff *data21 = skb_clone(data18, flags);
	struct sk_buff *data22 = skb_unshare(data18, flags);
	struct net_device *dev23 = ldv_undef_ptr_non_null();
	unsigned int length23 = ldv_undef_uint();
	struct sk_buff *data23 = __netdev_alloc_skb(dev23, length23, flags);
	int newheadroom24 = ldv_undef_int();
	int newtailroom24 = ldv_undef_int();
	struct sk_buff *data24 = skb_copy_expand(data18, newheadroom24, newtailroom24, flags);
	int nhead25 = ldv_undef_int();
	int ntail25 = ldv_undef_int();
	int data25 = pskb_expand_head(data18, nhead25, ntail25, flags);
	struct usb_device *dev26 = ldv_undef_ptr();
	size_t size26 = ldv_undef_uint();
	dma_addr_t dma26;
	void *data26 = usb_alloc_coherent(dev26, size26, flags, &dma26);
	int iso_packets27 = ldv_undef_int();
	struct urb *data27 =  usb_alloc_urb(iso_packets27, flags);
	int data28 = usb_submit_urb(data27, flags);
	int sum;

	/* To overcome warnings about unused variables. */
	sum = data10 + data25 + data28;

	usb_free_urb(data27);
	usb_free_coherent(dev26, size26, data26, dma26);
	kfree_skb(data24);
	kfree_skb(data23);
	kfree_skb(data22);
	kfree_skb(data21);
	kfree_skb(data20);
	kfree_skb(data19);
	kfree_skb(data18);
	kfree_skb(data17);
	kfree(data16);
	kfree(data15);
	kfree(data14);
	free_pages(data13, order13);
	__free_pages(data12, order12);
	__free_pages(data11, order11);
	mempool_free(data9, pool9);
	kfree(data8);
	kfree(data7);
	kfree(data6);
	kfree(data5);
	kfree(data4);
	kfree(data3);
	kfree(data2);
	kfree(data1);
}

static inline void ldv_nonatomic_alloc(void)
{
	unsigned long size = ldv_undef_ulong();
	int node = ldv_undef_int();
	void *data1 = vmalloc(size);
	void *data2 = vzalloc(size);
	void *data3 = vmalloc_user(size);
	void *data4 = vmalloc_node(size, node);
	void *data5 = vzalloc_node(size, node);
	void *data6 = vmalloc_exec(size);
	void *data7 = vmalloc_32(size);
	void *data8 = vmalloc_32_user(size);

	kfree(data1);
	kfree(data2);
	kfree(data3);
	kfree(data4);
	kfree(data5);
	kfree(data6);
	kfree(data7);
	kfree(data8);
}
