#include <linux/types.h>
#include <verifier/common.h>
#include <verifier/nondet.h>
#include <verifier/memory.h>

void *ldv_malloc(size_t size)
{
    void *res = ldv_undef_ptr();
    ldv_assume(res != NULL);
    return res;
}

void *ldv_calloc(size_t nmemb, size_t size)
{
    void *res = ldv_undef_ptr();
    ldv_assume(res != NULL);
    return res;
}

void *ldv_zalloc(size_t size)
{
    void *res = ldv_undef_ptr();
    ldv_assume(!ldv_is_err(res));
    return res;
}
