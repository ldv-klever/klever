#include <verifier/rcv.h>

/* Module locks counter (1 is the initial state; it shouldn't go lower). We do not distinguish different modules */
int ldv_module_refcounter = 1;

/* MODEL_FUNC_DEF Increment module reference counter (unless the module pointer is NULL) */
void ldv_module_get(struct module *module)
{
	/* OTHER Do nothing if the module pointer is NULL */
	if (module)
	{
		/* LDV_COMMENT_CHANGE_STATE Increment module reference counter */
		ldv_module_refcounter++;
	}
}

/* MODEL_FUNC_DEF Try to get module. The operation may succeed and return 1, or fail and return 0 */
int ldv_try_module_get(struct module *module)
{
	int module_get_succeeded;

	/* OTHER Do nothing if the module pointer is NULL */
	if (module)
	{
		/* OTHER Model success or failure of getting the module */
		module_get_succeeded = ldv_undef_int();

		if (module_get_succeeded == 1)
		{
			/* LDV_COMMENT_CHANGE_STATE Increment module reference counter */
			ldv_module_refcounter++;
			/* RETURN Return 1 telling about success */
			return 1;
		}
		else
		{
			/* RETURN Return 0 telling that module get has failed */
			return 0;
		}
	}
}

/* MODEL_FUNC_DEF Put module (unless module pointer is zero). Check if the module reference counter was greater than zero */
void ldv_module_put(struct module *module)
{
	/* OTHER Do nothing if the module pointer is NULL */
	if (module)
	{
		/* ASSERT This assertion fails if the module was put more times than it was got */
		ldv_assert(ldv_module_refcounter > 1);
		/* LDV_COMMENT_CHANGE_STATE Decrease reference counter thus putting the module */
		ldv_module_refcounter--;
	}
}

/* MODEL_FUNC_DEF Put the module and stop execution */
void ldv_module_put_and_exit(void)
{
	ldv_module_put((struct module*)1);
	/* OTHER Stop execution */
	LDV_STOP: goto LDV_STOP;
}

/* MODEL_FUNC_DEF Get the reference counter of the module */
unsigned int ldv_module_refcount(void)
{
	/* RETURN Return reference counter */
	return ldv_module_refcounter - 1;
}

/* MODEL_FUNC_DEF At the end of execution, module reference counter must be the same as at the beginning */
void ldv_check_final_state(void)
{
	/* ASSERT If this assertion is violated, then the module was put somewhere duiring the execution, and wasn't got! */
	ldv_assert(ldv_module_refcounter == 1);
}