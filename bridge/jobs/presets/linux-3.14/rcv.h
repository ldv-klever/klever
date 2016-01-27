#ifndef _LDV_RCV_H_
#define _LDV_RCV_H_

bool ldv_check_retval(int retval)
{
  bool comparison;
  comparison = (retval == 0);
  return comparison;
}

/* If expr evaluates to zero, ldv_assert() causes a program to reach the error
   label like the standard assert(). */
#define ldv_assert(expr) ((expr) ? 0 : ldv_error())

/* The error label wrapper. It is used because of some static verifiers (like
   BLAST) don't accept multiple error labels through a program. */
static inline void ldv_error(void)
{
  LDV_ERROR: goto LDV_ERROR;
}

/* If expr evaluates to zero, ldv_assume() causes an infinite loop that is
   avoided by verifiers. */
#define ldv_assume(expr) ((expr) ? 0 : ldv_stop())

/* Check that error has not been found until there */
void ldv_check_final_state(void);

/* Infinite loop, that causes verifiers to skip such paths. */
static inline void ldv_stop(void) {
  LDV_STOP: goto LDV_STOP;
}

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

/* Add explicit model for __builin_expect GCC function. Without the model a
   return value will be treated as nondetermined by verifiers. */
long __builtin_expect(long exp, long c)
{
  return exp;
}

/* This function causes the program to exit abnormally. GCC implements this
function by using a target-dependent mechanism (such as intentionally executing
an illegal instruction) or by calling abort. The mechanism used may vary from
release to release so you should not rely on any particular implementation.
http://gcc.gnu.org/onlinedocs/gcc/Other-Builtins.html */
void __builtin_trap(void)
{
  ldv_assert(0);
}

/* The constant is for simulating an error of ldv_undef_ptr() function. */
#define LDV_PTR_MAX 2012

#endif /* _LDV_RCV_H_ */
