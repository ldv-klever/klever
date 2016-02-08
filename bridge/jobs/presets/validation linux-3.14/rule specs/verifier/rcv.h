#ifndef _LDV_RCV_H_
#define _LDV_RCV_H_

/* If expr evaluates to zero, ldv_assert() causes a program to reach the error
 * function call like the standard assert().
 */
#define ldv_assert(expr) ((expr) ? 0 : __VERIFIER_error())

/* http://sv-comp.sosy-lab.org/2015/rules.php */
void __VERIFIER_error(void);

#define ldv_assume(expr) __VERIFIER_assume(expr)

/* http://sv-comp.sosy-lab.org/2015/rules.php */
void __VERIFIER_assume(int expr);

/* Check that error has not been found until there. */
void ldv_check_final_state(void);

/* Special nondeterministic functions. */
int ldv_undef_int(void);
void *ldv_undef_ptr(void);
unsigned long ldv_undef_ulong(void);
/* Return nondeterministic negative integer number. */
static inline int ldv_undef_int_negative(void)
{
	int ret = ldv_undef_int();
	ldv_assume(ret < 0);
	return ret;
}
/* Return nondeterministic nonpositive integer number. */
static inline int ldv_undef_int_nonpositive(void)
{
	int ret = ldv_undef_int();
	ldv_assume(ret <= 0);
	return ret;
}

/* Explicit model for GCC function __builin_expect(). Without this model
 * return value of __builtin_expect() will be treated as nondetermined by
 * verifiers.
 */
long __builtin_expect(long exp, long c)
{
	return exp;
}

/* This function causes the program to exit abnormally. GCC implements this
 * function by using a target-dependent mechanism (such as intentionally
 * executing an illegal instruction) or by calling abort. The mechanism used
 * may vary from release to release so you should not rely on any particular
 * implementation (http://gcc.gnu.org/onlinedocs/gcc/Other-Builtins.html).
 */
void __builtin_trap(void)
{
	ldv_assert(0);
}

/* Pointers greater then this number correspond to errors. */
#define LDV_PTR_MAX 2012

#endif /* _LDV_RCV_H_ */
