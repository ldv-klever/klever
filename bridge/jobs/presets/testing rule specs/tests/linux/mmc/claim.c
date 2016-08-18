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
#include <linux/kernel.h>
#include <linux/mutex.h>
#include <linux/mmc/sdio_func.h>
#include <linux/mmc/host.h>
#include <linux/mmc/card.h>
#include <linux/wait.h>

/* This test verifies that an error is raised when an sdio_func is claimed but wasn't released again before the end. */
int __init my_init(void)
{
	struct mmc_host* test_host = mmc_alloc_host(0, 0);
	struct mmc_host* test_host1 = mmc_alloc_host(0,0);
	struct mmc_card test_card;
	struct mmc_card test_card1;
	struct sdio_func test_func;
	struct sdio_func test_func1;

	test_card.type = MMC_TYPE_SDIO;
	test_card1.type = MMC_TYPE_SDIO;

	test_card.host = test_host;
	test_func.card = &test_card;
	test_card1.host = test_host1;
	test_func1.card = &test_card1;

	test_func.card->host->index = 1;
	test_func1.card->host->index = 2;
	test_func.device = 1;
	test_func1.device = 2;

	sdio_claim_host(&test_func);

	return 0;
}

module_init(my_init);
