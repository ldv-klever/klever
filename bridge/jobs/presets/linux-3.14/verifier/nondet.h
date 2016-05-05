#ifndef __VERIFIER_NONDET_H
#define __VERIFIER_NONDET_H

/* Special nondeterministic functions. */
extern int ldv_undef_int(void);
extern void *ldv_undef_ptr(void);
extern unsigned long ldv_undef_ulong(void);

/* Return nondeterministic negative integer number. */
extern int ldv_undef_int_negative(void);

/* Return nondeterministic nonpositive integer number. */
extern int ldv_undef_int_nonpositive(void);

#endif /* __VERIFIER_NONDET_H */
