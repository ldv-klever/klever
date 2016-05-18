#include <linux/ldv/common.h>
#include <verifier/common.h>

/* There are 2 possible model states. */
enum
{
	LDV_PROBE_ZERO_STATE = 0, /* No error occured. */
	LDV_PROBE_ERROR = 1,      /* Error occured. probe() should return error code (or at least not zero). */
};

/* CHANGE_STATE Model automaton state (one of two possible ones) */
int ldv_probe_state = LDV_PROBE_ZERO_STATE;

// TODO: differentiate 2 functions by bug kinds

/* MODEL_FUNC_DEF Nondeterministically change state after call to usb_register() */
int ldv_usb_register(void)
{
	int nondet;

	/* OTHER Nondeterministically report error */
	if (nondet < 0)
	{
		/* CHANGE_STATE Error occured */
		ldv_probe_state = LDV_PROBE_ERROR;
		/* RETURN Return error code */
		return nondet;
	}
	else
	{
		/* RETURN Assume no error occured */
		return 0;
	}
}

/* MODEL_FUNC_DEF Nondeterministically change state after call to register_netdev() */
int ldv_register_netdev(void)
{
	int nondet;

	/* OTHER Nondeterministically report error */
	if (nondet < 0)
	{
		/* CHANGE_STATE Error occured */
		ldv_probe_state = LDV_PROBE_ERROR;
		/* RETURN Return error code */
		return nondet;
	}
	else
	{
		/* RETURN Assume no error occured */
		return 0;
	}
}

/* MODEL_FUNC_DEF Check that error code was properly propagated in probe() */
void ldv_check_return_value_probe(int retval)
{
	if (ldv_probe_state == LDV_PROBE_ERROR)
	{
		/* ASSERT Errors of usb_register() and register_netdev() should be properly propagated */
		ldv_assert(retval != 0);
	}
}
