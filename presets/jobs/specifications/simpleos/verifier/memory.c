#include <kernel.h>
#include <../verifier/reference memory.c>

void *ldv_malloc(size_t size)
{
    return ldv_reference_malloc(size);
}

void *ldv_xmalloc(size_t size)
{
    return ldv_reference_xmalloc(size);
}

void ldv_free(void *s)
{
    ldv_reference_free(s);
}
