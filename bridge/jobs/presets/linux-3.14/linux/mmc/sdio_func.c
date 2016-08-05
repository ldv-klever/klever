#include <linux/mmc/sdio_func.h>
#include <linux/mmc/host.h>
#include <linux/mmc/card.h>
#include <linux/ldv/common.h>
#include <verifier/common.h>

/* CHANGE_STATE SDIO bus is unclaimed */
unsigned short ldv_sdio_element = 0;

/* MODEL_FUNC_DEF Check that SDIO bus was claimed */
void ldv_check_context(struct sdio_func *func)
{
	/* ASSERT SDIO bus should be claimed before usage */
	ldv_assert("linux:mmc:sdio_func::wrong params", ldv_sdio_element == func->card->host->index);
}

/* MODEL_FUNC_DEF Check that SDIO bus was not claimed */
void ldv_sdio_claim_host(struct sdio_func *func)
{
	/* ASSERT SDIO bus should be unclaimed */
	ldv_assert("linux:mmc:sdio_func::double claim", ldv_sdio_element == 0);

	/* CHANGE_STATE Claim SDIO bus (remember device that does this) */
	ldv_sdio_element = func->card->host->index;
}

/* MODEL_FUNC_DEF Check that SDIO bus was claimed by the same device */
void ldv_sdio_release_host(struct sdio_func *func)
{
	/* ASSERT SDIO bus was claimed by the same device */
	ldv_assert("linux:mmc:sdio_func::release without claim", ldv_sdio_element == func->card->host->index);

	/* CHANGE_STATE Release SDIO bus */
	ldv_sdio_element = 0;
}
/* MODEL_FUNC_DEF Check that SDIO bus is not claimed at the end */
void ldv_check_final_state(void)
{
	/* ASSERT SDIO bus should be released before finishing operation */
	ldv_assert("linux:mmc:sdio_func::unreleased at exit", ldv_sdio_element == 0);
}
