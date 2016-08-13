#include <linux/ldv/common.h>
#include <verifier/common.h>

int ldv_dma_calls = 0;

/* MODEL_FUNCTION_DEFINITION Map page */
void ldv_dma_map_page(void) {
	/* ASSERT Check that previous dma_mapping call was checked */
	ldv_assert("linux:dma::double map", ldv_dma_calls == 0);
	/* CHANGE_STATE Increase map counter */
	ldv_dma_calls++;
}

/* MODEL_FUNCTION_DEFINITION Unmap page */
void ldv_dma_mapping_error(void) {
	/* ASSERT No dma_mapping calls to verify */				
	ldv_assert("linux:dma::unmap before map", ldv_dma_calls > 0);
	ldv_dma_calls--;
}

/* MODEL_FUNC_DEF Map page */
void ldv_dma_map_single(void) {
	/* ASSERT Check that previous dma_mapping call was checked */
	ldv_assert("linux:dma::double map", ldv_dma_calls == 0);
	/* CHANGE_STATE Increase map counter */
	ldv_dma_calls++;
}
	
/* MODEL_FUNC_DEF Map page */
void ldv_dma_map_single_attrs(void) {
	/* ASSERT Check that previous dma_mapping call was checked */
	ldv_assert("linux:dma::double map", ldv_dma_calls == 0);
	/* CHANGE_STATE Increase map counter */
	ldv_dma_calls++;
}

/* MODEL_FUNC_DEF Check that all module reference counters have their initial values at the end */
void ldv_check_final_state(void) {
	/* ASSERT All incremented module reference counters should be decremented before module unloading*/
	ldv_assert("linux:dma::more initial at exit", ldv_dma_calls == 0);
}
