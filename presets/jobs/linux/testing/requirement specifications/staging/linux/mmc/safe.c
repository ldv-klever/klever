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

/* This is a safe test for requirement 0150 to verify that the implementation is working correctly and it supports multiple nested claims. */
static int __init ldv_init(void)
{
	int *err_ret = kmalloc(sizeof(int), 0);
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

	sdio_claim_host(&func);
	printk(KERN_DEBUG "two sdio func claimed\n");

	sdio_enable_func(&func);
	sdio_disable_func(&func);
	sdio_claim_irq(	&func, handler);
	sdio_release_irq(&func);
	sdio_readb(&func, 0, err_ret);
	sdio_readw(&func, 0, err_ret);
	sdio_readl(&func, 0, err_ret);
	sdio_readsb(&func, 0, 0, 0);
	sdio_writeb(&func, 0, 0 ,err_ret);
	sdio_writew(&func, 0, 0, err_ret);
	sdio_writel(&func, 0, 0, err_ret);
	sdio_writesb(&func, 0, 0, 0);
	sdio_writeb_readb(&func, 0, 0, err_ret);
	sdio_memcpy_fromio(&func, 0 , 0, 0);
	sdio_memcpy_toio(&func, 0, 0, 0);
	sdio_f0_readb(&func, 0, err_ret);
	sdio_f0_writeb(&func, 0, 0 ,err_ret);

	sdio_release_host(&func);
	sdio_claim_host(&func);
	sdio_release_host(&func);

	sdio_claim_host(&func1);
	sdio_release_host(&func1);

	return 0;
}

module_init(ldv_init);
