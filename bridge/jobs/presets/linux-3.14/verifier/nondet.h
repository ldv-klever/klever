/*
 * Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
 * Ivannikov Institute for System Programming of the Russian Academy of Sciences
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * ee the License for the specific language governing permissions and
 * limitations under the License.
 */

#ifndef __VERIFIER_NONDET_H
#define __VERIFIER_NONDET_H


/* Special nondeterministic functions. */
extern int ldv_undef_int(void);
extern int ldv_undef_long(void);
extern unsigned int ldv_undef_uint(void);
extern unsigned long ldv_undef_ulong(void);
extern unsigned long long ldv_undef_ulonglong(void);
extern void *ldv_undef_ptr(void);

/* Return nondeterministic positive integer number. */
extern int ldv_undef_int_positive(void);

/* Return nondeterministic negative integer number. */
extern int ldv_undef_int_negative(void);

/* Return nondeterministic nonpositive integer number. */
extern int ldv_undef_int_nonpositive(void);

/* Return nondeterministic non-null pointer. */
extern void *ldv_undef_ptr_non_null(void);

#endif /* __VERIFIER_NONDET_H */
