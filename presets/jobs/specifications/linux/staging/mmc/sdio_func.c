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

#include <linux/mmc/sdio_func.h>
#include <linux/mmc/host.h>
#include <linux/mmc/card.h>
#include <linux/ldv/common.h>
#include <verifier/common.h>

/* NOTE SDIO bus is unclaimed */
unsigned short ldv_sdio_element = 0;

void ldv_check_context(struct sdio_func *func)
{
	/* ASSERT SDIO bus should be claimed before usage */
	ldv_assert(ldv_sdio_element == func->card->host->index);
}

void ldv_sdio_claim_host(struct sdio_func *func)
{
	/* ASSERT SDIO bus should be unclaimed */
	ldv_assert(ldv_sdio_element == 0);

	/* NOTE Claim SDIO bus (remember device that does this) */
	ldv_sdio_element = func->card->host->index;
}

void ldv_sdio_release_host(struct sdio_func *func)
{
	/* ASSERT SDIO bus was claimed by the same device */
	ldv_assert(ldv_sdio_element == func->card->host->index);

	/* NOTE Release SDIO bus */
	ldv_sdio_element = 0;
}

void ldv_check_final_state(void)
{
	/* ASSERT SDIO bus should be released before finishing operation */
	ldv_assert(ldv_sdio_element == 0);
}
