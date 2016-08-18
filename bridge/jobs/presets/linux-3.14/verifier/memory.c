#include <linux/types.h>
#include <linux/ldv/err.h>
#include <verifier/common.h>
#include <verifier/nondet.h>
#include <verifier/memory.h>

/* ISO/IEC 9899:1999 specification. p. 313, § 7.20.3 "Memory management functions". */
extern void *malloc(size_t size);
extern void *calloc(size_t nmemb, size_t size);
extern void free(void *);

void *ldv_malloc(size_t size)
{
	if (ldv_undef_int()) {
		void *res = malloc(size);
		ldv_assume(res != NULL);
		ldv_assume(!ldv_is_err(res));
		return res;
	}
	else {
		return NULL;
	}
}

void *ldv_calloc(size_t nmemb, size_t size)
{
	if (ldv_undef_int()) {
		void *res = calloc(nmemb, size);
		ldv_assume(res != NULL);
		ldv_assume(!ldv_is_err(res));
		return res;
	}
	else {
		return NULL;
	}
}

void *ldv_zalloc(size_t size)
{
	return ldv_calloc(1, size);
}

void ldv_free(void *s)
{
	free(s);
}

void *ldv_xmalloc(size_t size)
{
    void *res = malloc(size);
    ldv_assume(res != NULL);
    ldv_assume(!ldv_is_err(res));
    return res;
}

void *ldv_malloc_unknown_size(void)
{
	if (ldv_undef_int()) {
		void *res = ldv_undef_ptr();
		ldv_assume(res != NULL);
		ldv_assume(!ldv_is_err(res));
		return res;
	}
	else {
		return NULL;
	}
}

void *ldv_calloc_unknown_size(void)
{
	if (ldv_undef_int()) {
		void *res = ldv_undef_ptr();
		ldv_assume(res != NULL);
		ldv_assume(!ldv_is_err(res));
		return res;
	}
	else {
		return NULL;
	}
}

void *ldv_zalloc_unknown_size(void)
{
	return ldv_calloc_unknown_size();
}

void *ldv_xmalloc_unknown_size(size_t size)
{
	void *res = ldv_undef_ptr();
	ldv_assume(res != NULL);
	ldv_assume(!ldv_is_err(res));
	return res;
}
