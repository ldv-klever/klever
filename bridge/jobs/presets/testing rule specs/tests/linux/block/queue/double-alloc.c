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
#include <linux/blkdev.h>
#include <linux/types.h>

int __init my_init(void)
{
	request_fn_proc *r;
	spinlock_t *spin;
	gfp_t flags;
	struct request_queue *queue = blk_init_queue(r, spin);
	queue = blk_alloc_queue(flags);
	if (queue)
	{
		blk_cleanup_queue(queue);
	}

	return 0;
}

module_init(my_init);
