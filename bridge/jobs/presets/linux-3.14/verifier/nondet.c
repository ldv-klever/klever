#include <verifier/common.h>
#include <verifier/nondet.h>

int ldv_undef_int_negative(void)
{
	int ret = ldv_undef_int();
	ldv_assume(ret < 0);
	return ret;
}

int ldv_undef_int_nonpositive(void)
{
	int ret = ldv_undef_int();
	ldv_assume(ret <= 0);
	return ret;
}
