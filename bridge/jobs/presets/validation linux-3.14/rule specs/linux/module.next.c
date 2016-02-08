/* NOTE: include headers by analogy with mutex.c. */
#include <linux/kernel.h>
#include <linux/module.h>
#include <verifier/rcv.h>

/* Module reference counter that shouldn't go lower its initial state. We do not distinguish different modules. */
int ldv_module_refcounter;

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
		if (ldv_undef_int())
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
		ldv_assert(ldv_module_refcounter > 0);
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
	ldv_assume(0);
}

/* MODEL_FUNC_DEF Get module reference counter */
unsigned int ldv_module_refcount(void)
{
	/* RETURN Return module reference counter */
	return ldv_module_refcounter;
}

/* NOTE: use 0 as initial value instead of 1 and perform initialization in ldv_initialize() rather than globally (like in mutex.c). */
/* MODEL_FUNC_DEF Set module reference counter initial value at the beginning */
void ldv_initialize(void)
{
	/* CHANGE_STATE Set module reference counter initial value at the beginning */
	ldv_module_refcounter = 0;
}

/* MODEL_FUNC_DEF Check that module reference counter has its initial value at the end */
void ldv_check_final_state(void)
{
	/* ASSERT Module reference counter should be decremented to its initial value before finishing operation */
	ldv_assert(ldv_module_refcounter == 0);
}
