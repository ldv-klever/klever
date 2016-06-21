#include <linux/ldv/common.h>
#include <verifier/common.h>

/* Module reference counter that shouldn't go lower its initial state. We do not distinguish different modules. */
/* CHANGE_STATE Set module reference counter initial value at the beginning */	
int ldv_module_refcounter = 1;

/* MODEL_FUNC_DEF Increment module reference counter unless module pointer is NULL */
void ldv_module_get(struct module *module)
{
	/* OTHER Do nothing if module pointer is NULL */
	if (module)
	{
		/* CHANGE_STATE Increment module reference counter */
		ldv_module_refcounter++;
	}
}

/* MODEL_FUNC_DEF Nondeterministically increment module reference counter unless module pointer is NULL */
int ldv_try_module_get(struct module *module)
{
	/* OTHER Do nothing if module pointer is NULL */
	if (module)
	{
		/* OTHER Nondeterministically increment module reference counter */
		if (ldv_undef_int() == 1)
		{
			/* CHANGE_STATE Increment module reference counter */
			ldv_module_refcounter++;
			/* RETURN Successfully incremented module reference counter */
			return 1;
		}
		else
		{
			/* RETURN Could not increment module reference counter */
			return 0;
		}
	}
}

/* MODEL_FUNC_DEF Check that module reference counter is greater than its initial state and decrement it unless module pointer is NULL */
void ldv_module_put(struct module *module)
{
	/* OTHER Do nothing if module pointer is NULL */
	if (module)
	{
		/* ASSERT Decremented module reference counter should be greater than its initial state */
		ldv_assert("linux:module:resource:less initial decrement", ldv_module_refcounter > 1);
		/* CHANGE_STATE Decrement module reference counter */
		ldv_module_refcounter--;
	}
}

/* MODEL_FUNC_DEF Check that module reference counter is greater than its initial state, decrement it and stop execution */
void ldv_module_put_and_exit(void)
{
	/* MODEL_FUNC_CALL Decrement module reference counter */ 
	ldv_module_put((struct module *)1);
	/* OTHER Stop execution */
	LDV_STOP: goto LDV_STOP;
}

/* MODEL_FUNC_DEF Get module reference counter */
unsigned int ldv_module_refcount(void)
{
	/* RETURN Return module reference counter */
	return ldv_module_refcounter - 1;
}

/* MODEL_FUNC_DEF Check that module reference counter has its initial value at the end */
void ldv_check_final_state(void)
{
	/* ASSERT Module reference counter should be decremented to its initial value before finishing operation */
	ldv_assert("linux:module:resource:more initial at exit", ldv_module_refcounter == 1);
}
