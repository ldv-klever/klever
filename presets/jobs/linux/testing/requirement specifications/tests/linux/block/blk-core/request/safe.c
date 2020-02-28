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

static int __init ldv_init(void)
{
	struct request_queue *q1 = ldv_undef_ptr(), *q2 = ldv_undef_ptr();
	int rw = ldv_undef_int();
	struct bio *bio = ldv_undef_ptr();
	gfp_t gfp_mask1 = ldv_undef_uint(), gfp_mask2 = ldv_undef_uint();
    struct request *request1, *request2;

	request1 = blk_get_request(q1, rw, gfp_mask1);
	if (request1)
		blk_put_request(request1);

	request2 = blk_make_request(q2, bio, gfp_mask2);
	if (!IS_ERR(request2))
		__blk_put_request(q2, request2);

	return 0;
}

module_init(ldv_init);
