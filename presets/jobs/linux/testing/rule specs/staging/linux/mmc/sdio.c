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
#include <linux/slab.h>
irqreturn_t handler(void){return IRQ_HANDLED;}

/* This tests that sdio_f0_readb can't be done without sdio_func being already claimed before. */
static int __init ldv_init(void)
{
	int *err_ret = kmalloc(sizeof(int), 0);
	struct mmc_host *mmc;
	struct mmc_card card;
	struct sdio_func func;

	mmc = mmc_alloc_host(0, 0);
	card.type = MMC_TYPE_SDIO;
	card.host = mmc;
	func.card = &card;
	func.card->host->index=1;
	func.device = 1;

	sdio_f0_readb(&func, 0, err_ret);

	return 0;
}

module_init(ldv_init);
