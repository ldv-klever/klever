#ifndef _LDV_SET_H_
#define _LDV_SET_H_

#if defined(LDV_SETS_MODEL_FLAG)
typedef _Bool Set;
typedef void *Element;
# define ldv_set_init(set) (set = 0)
# define ldv_set_add(set, element) (set = 1)
# define ldv_set_remove(set, element) (set = 0)
# define ldv_set_contains(set, element) (set == 1)
# define ldv_set_is_empty(set) (set == 0)
#elif defined(LDV_SETS_MODEL_COUNTER)
typedef int Set;
typedef void *Element;
# define ldv_set_init(set) (set = 0)
# define ldv_set_add(set, element) (set++)
# define ldv_set_remove(set, element) (set--)
# define ldv_set_contains(set, element) (set != 0)
# define ldv_set_is_empty(set) (set == 0)
#elif defined(LDV_SETS_MODEL_NONNEGATIVE_COUNTER)
typedef unsigned int Set;
typedef void *Element;
# define ldv_set_init(set) (set = 0)
# define ldv_set_add(set, element) (set++)
# define ldv_set_remove(set, element) ((set == 0) ?: set--)
# define ldv_set_contains(set, element) (set != 0)
# define ldv_set_is_empty(set) (set == 0)
#else
# error "Sets are likely used but sets model is not specified"
#endif

#endif /* _LDV_SET_H_ */
