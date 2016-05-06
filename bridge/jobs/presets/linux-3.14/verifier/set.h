#ifndef __VERIFIER_SET_H
#define __VERIFIER_SET_H

/* At the moment sets are represented just as counters, but this won't be the
 * case in future. */

/* Neither BLAST (with and without aliases), nor CPAchecker can't work with
 * even such a simple form of sets, since they don't support aliases.
typedef int *Set;
typedef void *Element;

static inline void ldv_set_init(Set set)
{
	*set = 0;
}

static inline void ldv_set_add(Set set, Element element)
{
	(*set)++;
}

static inline void ldv_set_remove(Set set, Element element)
{
	(*set)--;
}

static inline int ldv_set_contains(Set set, Element element)
{
	return *set != 0;
}

static inline int ldv_set_is_empty(Set set)
{
	return *set == 0;
}
*/

typedef int Set;
typedef void *Element;

#define ldv_set_init(set) (set = 0)
#define ldv_set_add(set, element) (set++)
#define ldv_set_remove(set, element) (set--)
#define ldv_set_contains(set, element) (set != 0)
#define ldv_set_is_empty(set) (set == 0)

#endif /* __VERIFIER_SET_H */
