#ifndef __VERIFIER_SET_H
#define __VERIFIER_SET_H

#if defined(LDV_SETS_MODEL_FLAG)
typedef _Bool ldv_set;
typedef void *ldv_set_element;
# define ldv_set_init(set) (set = 0)
# define ldv_set_add(set, element) (set = 1)
# define ldv_set_remove(set, element) (set = 0)
# define ldv_set_contains(set, element) (set == 1)
# define ldv_set_is_empty(set) (set == 0)
#elif defined(LDV_SETS_MODEL_COUNTER)
typedef int ldv_set;
typedef void *ldv_set_element;
# define ldv_set_init(set) (set = 0)
# define ldv_set_add(set, element) (set++)
# define ldv_set_remove(set, element) (set--)
# define ldv_set_contains(set, element) (set != 0)
# define ldv_set_is_empty(set) (set == 0)
#elif defined(LDV_SETS_MODEL_NONNEGATIVE_COUNTER)
typedef unsigned int ldv_set;
typedef void *ldv_set_element;
# define ldv_set_init(set) (set = 0)
# define ldv_set_add(set, element) (set++)
# define ldv_set_remove(set, element) ((set == 0) ?: set--)
# define ldv_set_contains(set, element) (set != 0)
# define ldv_set_is_empty(set) (set == 0)
#else
# error "Sets are likely used but sets model is not specified"
#endif

#endif /* __VERIFIER_SET_H */
