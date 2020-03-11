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
#include <linux/idr.h>
#include <verifier/nondet.h>

static int __init ldv_init(void)
{
	struct idr idp1, idp2;
	void *ptr1 = ldv_undef_ptr(), *found1, *ptr2 = ldv_undef_ptr(), *found2;
	int start1 = ldv_undef_int(), end1 = ldv_undef_int(), start2 = ldv_undef_int(), end2 = ldv_undef_int();
	gfp_t gfp_mask1 = ldv_undef_uint(), gfp_mask2 = ldv_undef_uint();

	idr_init(&idp1);
	idr_init(&idp2);

	idr_alloc(&idp1, ptr1, start1, end1, gfp_mask1);
	found1 = idr_find(&idp1, end1);
	idr_remove(&idp1, end1);
	idr_alloc(&idp1, ptr1, start1, end1, gfp_mask1);
	found1 = idr_find(&idp1, end1);
	idr_remove(&idp1, end1);
	idr_destroy(&idp1);

	idr_alloc(&idp2, ptr2, start2, end2, gfp_mask2);
	found2 = idr_find(&idp2, end2);
	idr_remove(&idp2, end2);
	idr_alloc(&idp2, ptr2, start2, end2, gfp_mask2);
	found2 = idr_find(&idp2, end2);
	idr_remove(&idp2, end2);
	idr_destroy(&idp2);

	return 0;
}

module_init(ldv_init);
