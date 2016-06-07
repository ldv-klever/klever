#include <verifier/common.h>
#include <verifier/memory.h>
#include <linux/ldv/common.h>
#include <linux/device.h>
#include <linux/kernel.h>
#include <linux/types.h>

/* LDV_COMMENT_CHANGE_STATE At the beginning nothing is allocated. */
int ldv_alloc_count = 0;

/* LDV_COMMENT_CHANGE_STATE Saved release function pointer. */
void (*gadget_release_pointer)(struct device *_dev);


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
	//functions, like memdup_user returns either valid pointer, or ptr_err
	ldv_assume(res != 0);
	if (res <= LDV_PTR_MAX) {
		/* CHANGE_STATE One more "memory" is allocated. */
		ldv_alloc_count++;
	}
	/* RETURN memory */
	return res;
}

/* MODEL_FUNC_DEF Free a "memory". */
void ldv_memory_free(void)
{
	/* CHANGE_STATE Free a "memory". */
	ldv_alloc_count--;
}

/* MODEL_FUNC_DEF Free a "memory". */
void ldv_save_gadget_release(void (*func)(struct device *_dev))
{
	gadget_release_pointer = func;
}

/* MODEL_FUNC_DEF All allocated memory should be freed at the end. */
void ldv_check_final_state(void)
{
	/* ASSERT Nothing should be allocated at the end. */
	ldv_assert("linux:alloc:resource:more at exit", ldv_alloc_count <= 0);
	ldv_assert("linux:alloc:resource:less at exit", ldv_alloc_count >= 0);
}