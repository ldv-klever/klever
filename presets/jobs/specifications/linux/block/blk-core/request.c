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
#include <ldv/linux/common.h>
#include <ldv/linux/err.h>
#include <ldv/verifier/common.h>
#include <ldv/verifier/nondet.h>

/* There are 2 possible states of blk request. */
enum
{
	LDV_BLK_RQ_ZERO_STATE, /* blk request isn't got. */
	LDV_BLK_RQ_GOT         /* blk request is got. */
};

/* NOTE At the beginning blk request is not got. */
int ldv_blk_rq = LDV_BLK_RQ_ZERO_STATE;

struct request *ldv_blk_get_request(gfp_t mask)
{
	struct request *res;

	if (ldv_blk_rq != LDV_BLK_RQ_ZERO_STATE)
		/* ASSERT blk request could be got just in case when it was not got before. */
		ldv_assert();

	/* NOTE Generate valid pointer or NULL. */
	res = (struct request *)ldv_undef_ptr();

	/* NOTE If gfp_mask argument has GFP_NOIO or GFP_KERNEL set, blk_get_request() cannot fail. */
	if (mask == GFP_KERNEL || mask == GFP_NOIO)
		ldv_assume(res != NULL);

	if (res != NULL) {
		/* NOTE Get blk request. */
		ldv_blk_rq = LDV_BLK_RQ_GOT;
	}

	return res;
}

struct request *ldv_blk_get_request_may_fail()
{
	struct request *res;

	if (ldv_blk_rq != LDV_BLK_RQ_ZERO_STATE)
		/* ASSERT blk request could be got just in case when it was not got before. */
		ldv_assert();

	/* NOTE Generate valid pointer or NULL. */
	res = (struct request *)ldv_undef_ptr();

	if (res != NULL) {
		/* NOTE Get blk request. */
		ldv_blk_rq = LDV_BLK_RQ_GOT;
	}

	return res;
}

struct request *ldv_blk_make_request(gfp_t mask)
{
	struct request *res;

	if (ldv_blk_rq != LDV_BLK_RQ_ZERO_STATE)
		/* ASSERT blk request could be got just in case when it was not got before. */
		ldv_assert();

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

void ldv_put_blk_rq(void)
{
	if (ldv_blk_rq != LDV_BLK_RQ_GOT)
		/* ASSERT blk request could be put just in case when it was got. */
		ldv_assert();

	/* NOTE Put blk request. */
	ldv_blk_rq = LDV_BLK_RQ_ZERO_STATE;
}

void ldv_check_final_state(void)
{
	if (ldv_blk_rq != LDV_BLK_RQ_ZERO_STATE)
		/* ASSERT blk request could not be got at the end. */
		ldv_assert();
}
