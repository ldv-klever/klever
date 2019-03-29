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
#include <linux/mmc/sdio_func.h>
#include <linux/mmc/host.h>
#include <linux/mmc/card.h>
#include <linux/wait.h>

/* This test verifies that an error is raised when an sdio_func is released but wasn't claimed in the first place. */
static int __init ldv_init(void)
{
	struct mmc_host *mmc;
	struct mmc_host *mmc1;
	struct mmc_card card;
	struct mmc_card card1;
	struct sdio_func func;
	struct sdio_func func1;

	mmc = mmc_alloc_host(0, 0);
	mmc1 = mmc_alloc_host(0, 0);
	card.type = MMC_TYPE_SDIO;
	card1.type = MMC_TYPE_SDIO;
	card.host = mmc;
	func.card = &card;
	card1.host = mmc1;
	func1.card = &card1;
	func.device = 1;
	func1.device = 2;
	func.card->host->index = 1;
	func1.card->host->index = 2;

	sdio_claim_host(&func);
	sdio_release_host(&func);

	sdio_release_host(&func1);

	return 0;
}

module_init(ldv_init);
