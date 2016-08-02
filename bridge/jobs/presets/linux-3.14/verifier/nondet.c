#include <verifier/common.h>
#include <verifier/nondet.h>
#include <linux/types.h>

/* SV-COMP functions intended for modelling nondeterminism. */
char __VERIFIER_nondet_char(void);
int __VERIFIER_nondet_int(void);
float __VERIFIER_nondet_float(void);
long __VERIFIER_nondet_long(void);
size_t __VERIFIER_nondet_size_t(void);
loff_t __VERIFIER_nondet_loff_t(void);
u32 __VERIFIER_nondet_u32(void);
u16 __VERIFIER_nondet_u16(void);
u8 __VERIFIER_nondet_u8(void);
unsigned char __VERIFIER_nondet_uchar(void);
unsigned int __VERIFIER_nondet_uint(void);
unsigned short __VERIFIER_nondet_ushort(void);
unsigned __VERIFIER_nondet_unsigned(void);
unsigned long __VERIFIER_nondet_ulong(void);
void *__VERIFIER_nondet_pointer(void);
void __VERIFIER_assume(int expression);

int ldv_undef_int(void) {
	return __VERIFIER_nondet_int();
}

void *ldv_undef_ptr(void) {
	return __VERIFIER_nondet_pointer();
}

unsigned long ldv_undef_ulong(void) {
	return __VERIFIER_nondet_ulong();
}

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
