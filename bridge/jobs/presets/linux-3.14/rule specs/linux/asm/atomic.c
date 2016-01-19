#include <linux/types.h>

/* MODEL_FUNC_DEF Add integer to atomic variable */
void ldv_atomic_add(int i, atomic_t *v)
{
	v->counter += i;
}

/* MODEL_FUNC_DEF Subtract integer from atomic variable */
void ldv_atomic_sub(int i, atomic_t *v)
{
	v->counter -= i;
}

/* MODEL_FUNC_DEF Subtract value from atomic variable and test result */
int ldv_atomic_sub_and_test(int i, atomic_t *v)
{
	v->counter -= i;
	if (v->counter)
	{
		return 0;
	}
	return 1;
}

/* MODEL_FUNC_DEF Increment atomic variable */
void ldv_atomic_inc(atomic_t *v)
{
	v->counter++;
}

/* MODEL_FUNC_DEF Decrement atomic variable */
void ldv_atomic_dec(atomic_t *v)
{
	v->counter--;
}

/* MODEL_FUNC_DEF Decrement atomic variable and test result */
int ldv_atomic_dec_and_test(atomic_t *v)
{
	v->counter--;
	if (v->counter)
	{
		return 0;
	}
	return 1;
}

/* MODEL_FUNC_DEF Increment atomic variable and test result */
int ldv_atomic_inc_and_test(atomic_t *v)
{
	v->counter++;
	if (v->counter)
	{
		return 0;
	}
	return 1;
}

/* MODEL_FUNC_DEF Add integer to atomic variable and return result */
int ldv_atomic_add_return(int i, atomic_t *v)
{
	v->counter+=i;
	return v->counter;
}

/* MODEL_FUNC_DEF Add integer to atomic variable and test result if negative */
int ldv_atomic_add_negative(int i, atomic_t *v)
{
	v->counter+=i;
	return v->counter < 0;
}

/* MODEL_FUNC_DEF Increment short integer and return result */
int ldv_atomic_inc_short(short int *v)
{
	*v = *v + 1;
	return *v;
}
