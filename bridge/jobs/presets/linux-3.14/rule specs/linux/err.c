#include <verifier/rcv.h>

/* MODEL_FUNC_DEF Check whether a given pointer represents an error */
long ldv_is_err(const void *ptr)
{
	/* RETURN Zero if a given pointer doesn't represent an error and non zero otherwise */
	return ((unsigned long)ptr > LDV_PTR_MAX);
}

/* MODEL_FUNC_DEF Convert a given error error to a pointer */
void *ldv_err_ptr(long error)
{
	/* RETURN Pointer representation of a given error */
	return (void *)(LDV_PTR_MAX - error);
}

/* MODEL_FUNC_DEF Convert a given pointer to an error */
long ldv_ptr_err(const void *ptr)
{
	/* RETURN Error */
	return (long)(LDV_PTR_MAX - (unsigned long)ptr);
}

/* MODEL_FUNC_DEF Check whether a given pointer represents an error or it is NULL */
long ldv_is_err_or_null(const void *ptr)
{
	/* RETURN Zero if a given pointer doesn't represents an error or it isn't NULL and non zero otherwise */
	return !ptr || ldv_is_err((unsigned long)ptr);
}
