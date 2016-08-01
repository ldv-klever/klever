#include <linux/ldv/common.h>
#include <verifier/common.h>
#include <verifier/nondet.h>
#include <linux/cpumask.h>

/* MODEL_FUNC_DEF Check offset value and return value between 0 and size. */
unsigned long ldv_find_next_bit(unsigned long size, unsigned long offset)
{
	/* ASSERT Offset should not be greater than size. */
	ldv_assert("linux:bitops::offset out of range", offset <= size);
	/* RETURN Return value between 0 and size. */
	unsigned long nondet = ldv_undef_ulong();
	ldv_assume (nondet <= size);
	ldv_assume (nondet >= 0);
	return nondet;
}

/* MODEL_FUNC_DEF Function returns value between 0 and size. */
unsigned long ldv_find_first_bit(unsigned long size)
{
	/* RETURN Return value between 0 and size. */
	unsigned long nondet = ldv_undef_ulong();
	ldv_assume (nondet <= size);
	ldv_assume (nondet >= 0);
	return nondet;
}

/* MODEL_FUNC_DEF Cut impossible pathes */
void ldv_initialize(void)
{
	ldv_assume(nr_cpu_ids > 0);
}