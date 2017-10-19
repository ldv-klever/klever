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

#include <linux/module.h>
#include <linux/dma-mapping.h>

static int __init init(void)
{
    struct device *dev;
    struct page *page;
    void *cpu_addr;
    void *ptr;
    struct dma_attrs *attrs;
    dma_addr_t map;

	map = dma_map_page(dev, page, 0, 1, DMA_BIDIRECTIONAL);
	if (dma_mapping_error(dev, map))
	    return -1;

	map = dma_map_single(dev, cpu_addr, 1, DMA_BIDIRECTIONAL);
	if (dma_mapping_error(dev, map))
	    return -1;

    map = dma_map_single_attrs(dev, ptr, 1, DMA_BIDIRECTIONAL, attrs);
	if (dma_mapping_error(dev, map))
	    return -1;

	return 0;
}

module_init(init);
