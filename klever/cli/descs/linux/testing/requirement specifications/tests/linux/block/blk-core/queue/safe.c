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
#include <linux/blkdev.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

static DEFINE_SPINLOCK(ldv_lock);

static void ldv_rfn(struct request_queue *q)
{
}

static int __init ldv_init(void)
{
	gfp_t gfp_mask = ldv_undef_uint();
	struct request_queue *queue1, *queue2;

	queue1 = blk_init_queue(ldv_rfn, &ldv_lock);
	ldv_assume(queue1 != NULL);
	blk_cleanup_queue(queue1);

	queue2 = blk_alloc_queue(gfp_mask);
	ldv_assume(queue2 != NULL);
	blk_cleanup_queue(queue2);

	return 0;
}

module_init(ldv_init);
