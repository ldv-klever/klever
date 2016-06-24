#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/mutex.h>
#include <linux/mmc/sdio_func.h>
#include <linux/mmc/host.h>
#include <linux/mmc/card.h>
#include <linux/wait.h>

/* This tests that sdio_disable_func can't be done without sdio_func being already claimed before. */
int __init my_init(void)
{
	struct mmc_host* test_host = mmc_alloc_host(0, 0);
	struct mmc_card test_card;
	struct sdio_func test_func;

	test_card.type = MMC_TYPE_SDIO;

	test_card.host = test_host;
	test_func.card = &test_card;

	test_func.device = 1;
	test_func.card->host->index=1;

	sdio_disable_func(&test_func);

	return 0;
}

module_init(my_init);
