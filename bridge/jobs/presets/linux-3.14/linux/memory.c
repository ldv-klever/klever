#include <linux/types.h>
#include <linux/ldv/common.h>
#include <verifier/common.h>
#include <verifier/memory.h>

/* CHANGE_STATE At the beginning nothing is allocated. */
int ldv_alloc_count = 0;

/* MODEL_FUNC_DEF Allocate a "memory". */
void ldv_after_alloc(void *res)
{
	ldv_assume(res <= LDV_PTR_MAX);
	if (res != 0) {
		/* CHANGE_STATE One more "memory" is allocated. */
		ldv_alloc_count++;
	}
}

/* MODEL_FUNC_DEF Allocate a non zero "memory", but can return PTR_ERR. */
void* ldv_nonzero_alloc(size_t size)
{
	void* res = ldv_malloc(size);
	ldv_after_alloc(res);
	// Functions, like memdup_user returns either valid pointer, or ptr_err.
	ldv_assume(res != 0);
	if (res <= LDV_PTR_MAX) {
		/* CHANGE_STATE One more "memory" is allocated. */
		ldv_alloc_count++;
	}
	/* RETURN Memory */
	return res;
}

/* MODEL_FUNC_DEF Free a "memory". */
void ldv_memory_free(void)
{
	/* CHANGE_STATE Free a "memory". */
	ldv_alloc_count--;
}

/* MODEL_FUNC_DEF All allocated memory should be freed at the end. */
void ldv_check_final_state(void)
{
	/* ASSERT Nothing should be allocated at the end. */
	ldv_assert("linux:alloc:resource::more at exit", ldv_alloc_count <= 0);
	ldv_assert("linux:alloc:resource::less at exit", ldv_alloc_count >= 0);
}
