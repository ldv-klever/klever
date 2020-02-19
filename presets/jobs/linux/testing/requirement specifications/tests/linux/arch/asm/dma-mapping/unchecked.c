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

#include <linux/module.h>
#include <linux/dma-mapping.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

static int __init ldv_init(void)
{
	gfp_t gfp_mask1 = ldv_undef_uint(), gfp_mask2 = ldv_undef_uint();
	struct page *page1, *page2;
	struct device *dev1 = ldv_undef_ptr_non_null(), *dev2 = ldv_undef_ptr_non_null();
	size_t offset1 = ldv_undef_uint(), size1 = ldv_undef_uint(), offset2 = ldv_undef_uint(), size2 = ldv_undef_uint();
	unsigned int dir1 = ldv_undef_uint(), dir2 = ldv_undef_uint();
    dma_addr_t map1, map2;

	page1 = alloc_page(gfp_mask1);
	ldv_assume(page1 != NULL);
	page2 = alloc_page(gfp_mask2);
	ldv_assume(page2 != NULL);

	map1 = dma_map_page(dev1, page1, offset1, size1, dir1);
	map2 = dma_map_page(dev2, page2, offset2, size2, dir2);

	__free_page(page2);
	__free_page(page1);

	return 0;
}

module_init(ldv_init);
