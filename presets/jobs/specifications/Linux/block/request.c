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

#include <linux/gfp.h>
#include <linux/ldv/common.h>
#include <linux/ldv/err.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

/* There are 2 possible states of blk request. */
enum
{
	LDV_BLK_RQ_ZERO_STATE, /* blk request isn't got. */
	LDV_BLK_RQ_GOT         /* blk request is got. */
};

/* NOTE At the beginning blk request is not got. */
int ldv_blk_rq = LDV_BLK_RQ_ZERO_STATE;

/* MODEL_FUNC Check that a blk request was not got and get it. Returns NULL if failed. */
struct request *ldv_blk_get_request(gfp_t mask)
{
	struct request *res;

	/* ASSERT blk request could be got just in case when it was not got before. */
	ldv_assert(ldv_blk_rq == LDV_BLK_RQ_ZERO_STATE);

	/* NOTE Generate valid pointer or NULL. */
	res = (struct request *)ldv_undef_ptr();

	/* NOTE If gfp_mask argument has __GFP_WAIT set, blk_get_request() cannot fail. */
	if (mask == __GFP_WAIT || mask == GFP_KERNEL || mask == GFP_NOIO)
		ldv_assume(res != NULL);

	if (res != NULL) {
		/* NOTE Get blk request. */
		ldv_blk_rq = LDV_BLK_RQ_GOT;
	}

	return res;
}

/* MODEL_FUNC Check that a blk request was not got and get it. Returns ERRPTR if failed. */
struct request *ldv_blk_make_request(gfp_t mask)
{
	struct request *res;

	/* ASSERT blk request could be got just in case when it was not got before. */
	ldv_assert(ldv_blk_rq == LDV_BLK_RQ_ZERO_STATE);

	/* NOTE Generate valid pointer or errptr. */
	res = (struct request *)ldv_undef_ptr();
	ldv_assume(res != NULL);

	/* NOTE Return valid pointer or NULL. */
	if (!ldv_is_err(res)) {
		/* NOTE Get blk request. */
		ldv_blk_rq = LDV_BLK_RQ_GOT;
	}

	return res;
}

/* MODEL_FUNC Check that a blk request was got and free it. */
void ldv_put_blk_rq(void)
{
	/* ASSERT blk request could be put just in case when it was got. */
	ldv_assert(ldv_blk_rq == LDV_BLK_RQ_GOT);
	/* NOTE Put blk request. */
	ldv_blk_rq = LDV_BLK_RQ_ZERO_STATE;
}

/* MODEL_FUNC All got blk requests should be put at the end. */
void ldv_check_final_state(void)
{
	/* ASSERT blk request could not be got at the end. */
	ldv_assert(ldv_blk_rq == LDV_BLK_RQ_ZERO_STATE);
}
