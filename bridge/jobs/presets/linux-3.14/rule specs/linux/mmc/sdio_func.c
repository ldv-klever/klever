#include <verifier/rcv.h>
#include <linux/mmc/sdio_func.h>
#include <linux/mmc/host.h>
#include <linux/mmc/card.h>

/* CHANGE_STATE SDIO bus is unclaimed */
unsigned short ldv_sdio_element = 0;

/* MODEL_FUNC_DEF Check that sdio function was claimed */
void ldv_check_context(struct sdio_func *func)
{
	/* ASSERT sdio function should be claimed before using it */
	ldv_assert(ldv_sdio_element == func->card->host->index);
}

/* MODEL_FUNC_DEF Check that the sdio bus hasn't already been claimed before */
void ldv_sdio_claim_host(struct sdio_func *func)
{
	/* ASSERT Check if the bus hasn't been claimed before */
	ldv_assert(ldv_sdio_element == 0);

	/* CHANGE_STATE The device that claimed the bus is equated to the state element */
	ldv_sdio_element = func->card->host->index;
}

/* MODEL_FUNC_DEF Checks the release of the bus and if it was claimed before by the same device releasing it */
void ldv_sdio_release_host(struct sdio_func *func)
{
	/* ASSERT Check if the device ordering the bus be released has already claimed it */
	ldv_assert(ldv_sdio_element == func->card->host->index);

	/* CHANGE_STATE Removing this device from the state element */
	ldv_sdio_element = 0;
}
/* MODEL_FUNC_DEF Check that SDIO bus isn't claimed at the end */
void ldv_check_final_state(void)
{
	/* ASSERT SDIO bus should be released before finishing operation */
	ldv_assert(ldv_sdio_element == 0);
}
