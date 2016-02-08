#include <verifier/rcv.h>

/* MODEL_FUNC_DEF Check whether pointer represents error */
long ldv_is_err(const void *ptr)
{
	/* RETURN Zero if pointer does not represent error and non zero otherwise */
	return ((unsigned long)ptr > LDV_PTR_MAX);
}

/* MODEL_FUNC_DEF Convert error to pointer */
void *ldv_err_ptr(long error)
{
	/* RETURN Pointer representation of error */
	return (void *)(LDV_PTR_MAX - error);
}

/* MODEL_FUNC_DEF Convert pointer to error */
long ldv_ptr_err(const void *ptr)
{
	/* RETURN Error */
	return (long)(LDV_PTR_MAX - (unsigned long)ptr);
}

/* MODEL_FUNC_DEF Check whether pointer represents error or it is NULL */
long ldv_is_err_or_null(const void *ptr)
{
	/* RETURN Zero if pointer does not represent error and it is not NULL and non zero otherwise */
	return !ptr || ldv_is_err((unsigned long)ptr);
}
