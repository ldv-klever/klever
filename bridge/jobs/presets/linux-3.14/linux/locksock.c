#include <linux/ldv/common.h>
#include <verifier/common.h>
#include <linux/types.h>
#include <verifier/nondet.h>

struct sock;

/* CHANGE_STATE There is no locked sockets at the beginning */
int locksocknumber = 0;

/* MODEL_FUNC_DEF executed after locking socket using nested function */
void ldv_past_lock_sock_nested(void)
{
/* CHANGE_STATE locking socket */
	locksocknumber++;
}

/* MODEL_FUNC_DEF executed around locking socket using fast function */
bool ldv_lock_sock_fast(void)
{
	/* OTHER we dont know lock this socket or not */
	if (ldv_undef_int())
	{
		/* CHANGE_STATE locking socket*/	
		locksocknumber++;
		/* RETURN Socket lock */
		return true; 
	}
	/* RETURN Cant lock socket */
	return false;
}

/* MODEL_FUNC_DEF executed around unlocking socket using fast function */
void ldv_unlock_sock_fast(void)
{
	/* ASSERT unlock_sock_fas negative locksocknumber the result of multiply releases */
	ldv_assert("linux:sock:double release", locksocknumber > 0);
	/* CHANGE_STATE unlocking socket fast warning*/
	locksocknumber--;
}

/* MODEL_FUNC_DEF executed after releasing socket */
void ldv_before_release_sock(void)
{
	/* ASSERT lock_sock negative locksocknumber the result of multiply releases */
	ldv_assert("linux:sock:double release", locksocknumber > 0);
	/* CHANGE_STATE locked socket released */
	locksocknumber--;
}

/* MODEL_FUNC_DEF check on exit */
void ldv_check_final_state(void)
{
	/* ASSERT lock_sock number */
	ldv_assert("linux:sock:all locked sockets must be released", locksocknumber == 0);
}
