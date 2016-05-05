#include <verifier/rcv.h>

/* http://sv-comp.sosy-lab.org/2015/rules.php */
void __VERIFIER_error(void);

/* If expr evaluates to zero, ldv_assert() causes a program to reach the error
 * function call like the standard assert().
 */
void ldv_assert(int expression) {
    (expression) ? 0 : __VERIFIER_error();
}

void ldv_assume(int expression) {
    if (!expression) {
        /* Cut this path */
        ldv_assume_label:
        goto ldv_assume_label;
    }
}

void ldv_stop(void) {
    /* Stop analysis */
    ldv_stop_label:
    goto ldv_stop_label;
}

/* Return nondeterministic negative integer number. */
int ldv_undef_int_negative(void)
{
	int ret = ldv_undef_int();
	ldv_assume(ret < 0);
	return ret;
}

/* Return nondeterministic nonpositive integer number. */
int ldv_undef_int_nonpositive(void)
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
