#include <verifier/memory.h>
#include <verifier/rcv.h>

void *ldv_malloc(size_t size) {
    void *res = ldv_undef_ptr();
    ldv_assume(res);
    return res;
}

void *ldv_calloc(size_t nmemb, size_t size) {
    void *res = ldv_undef_ptr();
    ldv_assume(res);
    return res;
}