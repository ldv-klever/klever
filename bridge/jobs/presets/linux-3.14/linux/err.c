#include <verifier/memory.h>

long ldv_is_err(const void *ptr)
{
	return ((unsigned long)ptr > LDV_PTR_MAX);
}

void *ldv_err_ptr(long error)
{
	return (void *)(LDV_PTR_MAX - error);
}

long ldv_ptr_err(const void *ptr)
{
	return (long)(LDV_PTR_MAX - (unsigned long)ptr);
}

long ldv_is_err_or_null(const void *ptr)
{
	return !ptr || ldv_is_err((unsigned long)ptr);
}
