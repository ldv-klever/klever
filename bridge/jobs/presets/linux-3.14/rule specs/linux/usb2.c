#include <linux/kernel.h>
#include <verifier/rcv.h>

/* There are 3 possible model states. */
enum
{
	LDV_PROBE_ZERO_STATE = 0, /* No error occured. */
	LDV_PROBE_ERROR = 1,      /* Error occured. probe() should return error an code (or at least not zero). */
};

/* OTHER The model automaton state (one of thee possible ones) */
int ldv_probe_state = LDV_PROBE_ZERO_STATE;

/* MODEL_FUNC_DEF Non-deterministically change state after call to usb_register */
int ldv_usb_register(void)
{
	int nondet;

	/* LDV_COMMENT_OTHER Nondeterministically report an error */
	if (nondet < 0)
	{
		/* LDV_COMMENT_CHANGE_STATE Error occured */
		ldv_probe_state = LDV_PROBE_ERROR;
		/* LDV_COMMENT_RETURN Return an error */
		return nondet;
	}
	else if (nondet >= 0)
	{
		/* LDV_COMMENT_RETURN Assume no error occured */
		return 0;
	}
}

/* MODEL_FUNC_DEF Non-deterministically change state after call to register_netdev */
int ldv_register_netdev(void)
{
	int nondet;

	/* OTHER Nondeterministically report an error */
	if (nondet < 0)
	{
		/* CHANGE_STATE Error occured */
		ldv_probe_state = LDV_PROBE_ERROR;
		/* RETURN Return an error */
		return nondet;
	}
	else if (nondet >= 0)
	{
		/* RETURN Assume no error occured */
		return 0;
	}
}

/* MODEL_FUNC_DEF Check the error code was properly propagated in probe */
void ldv_check_return_value_probe(int retval)
{
	if (ldv_probe_state == LDV_PROBE_ERROR)
	{
		ldv_assert(retval != 0);
	}
}
