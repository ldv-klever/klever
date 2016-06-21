#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/mutex.h>
#include <linux/mmc/sdio_func.h>
#include <linux/mmc/host.h>
#include <linux/mmc/card.h>
#include <linux/wait.h>
#include <linux/slab.h>
irqreturn_t handler(void){return IRQ_HANDLED;}

/* This tests that sdio_memcpy_fromio can't be done without sdio_func being already claimed before. */
int __init my_init(void)
{
	int* err_ret = kmalloc(sizeof(int), 0);
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

	test_func.device=1;
	test_func1.device=2;

	sdio_memcpy_fromio(&test_func, 0, 0, 0);

	return 0;
}

module_init(my_init);
