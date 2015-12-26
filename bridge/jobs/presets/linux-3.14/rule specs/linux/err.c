#include <verifier/rcv.h>

/* MODEL_FUNC_DEF This function return result of checking if pointer is impossible */
long ldv_is_err(const void *ptr)
{
	/* RETURN Return value of function ldv_is_err_val() */
	return ((unsigned long)ptr > LDV_PTR_MAX);
}

/* MODEL_FUNC_DEF This function return pointer */
void *ldv_err_ptr(long error)
{
	/* RETURN Return error pointer */
	return (void *)(LDV_PTR_MAX - error);
}

/* MODEL_FUNC_DEF This function return error if pointer is impossible */
long ldv_ptr_err(const void *ptr)
{
	/* RETURN Return error code.*/
	return (long)(LDV_PTR_MAX - (unsigned long)ptr);
}

/* MODEL_FUNC_DEF This function check if pointer is impossible or null */
long ldv_is_err_or_null(const void *ptr)
{
	/* RETURN Return 0 if pointer is possible and not zero, and 1 in other cases */
	return 0;/*!ptr || ldv_is_err((unsigned long)ptr);*/
}
