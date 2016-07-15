#include <linux/types.h>
#include <linux/ldv/err.h>
#include <verifier/common.h>
#include <verifier/nondet.h>
#include <verifier/memory.h>

/*ISO/IEC 9899:1999 specification. p. 313, § 7.20.3 "Memory management functions"*/
extern void *malloc(size_t size);
extern void *calloc(size_t nmemb, size_t size);
extern void free(void *);

void *ldv_malloc(size_t size)
{
	void *res = ldv_verifier_malloc(size);
	ldv_assume(res != NULL);
	return res;
}

void *ldv_calloc(size_t nmemb, size_t size)
{
	void *res = ldv_verifier_calloc(nmemb, size);
	ldv_assume(res != NULL);
	return res;
}

void ldv_free(void *s)
{
	ldv_verifier_free(s);
}

void *ldv_verifier_malloc(size_t size)
{
	if(ldv_undef_int()) {
		void *res = malloc(size);
		ldv_assume(res != NULL);
		ldv_assume(!ldv_is_err(res));
		return res;
	} else {
		return 0;
	}
}

void *ldv_verifier_calloc(size_t nmemb, size_t size)
{
	if(ldv_undef_int()) {
		void *res = calloc(nmemb, size);
		ldv_assume(res != NULL);
		ldv_assume(!ldv_is_err(res));
		return res;
	} else {
		return 0;
	}
}

void *ldv_verifier_zalloc(size_t size)
{
	if(ldv_undef_int()) {
		void *res = calloc(1, size);
		ldv_assume(res != NULL);
		ldv_assume(!ldv_is_err(res));
		return res;
	} else {
		return 0;
	}
}

void ldv_verifier_free(void *s)
{
	free(s);
}