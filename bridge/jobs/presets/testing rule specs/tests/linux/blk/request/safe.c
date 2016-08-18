/*
 * Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
 * Institute for System Programming of the Russian Academy of Sciences
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
	struct request_queue *r;
	struct bio *bio;
	int x;
	gfp_t flags = __GFP_WAIT;
	struct request_queue *queue;

	struct request *request_1 = blk_get_request(r, x, flags);
	if (request_1)
		blk_put_request(request_1);
	else
		return -1;
//	struct request *request_2 = blk_make_request(r, bio, flags);
//	if (!IS_ERR(request_2))
//		__blk_put_request(queue, request_2);
	return 0;
}

module_init(my_init);
