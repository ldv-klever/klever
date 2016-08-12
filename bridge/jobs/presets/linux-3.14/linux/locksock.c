#include <linux/types.h>
#include <linux/ldv/common.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

struct sock;

/* CHANGE_STATE There is no locked sockets at the beginning */
int locksocknumber = 0;

/* MODEL_FUNC_DEF Lock socket */
void ldv_lock_sock(void)
{
	/* CHANGE_STATE locking socket */
	locksocknumber++;
}

/* MODEL_FUNC_DEF Try to lock socked and return true in case of success */
bool ldv_lock_sock_fast(struct sock *sk)
{
	/* OTHER we dont know lock this socket or not */
	if (ldv_undef_int()) {
		/* CHANGE_STATE locking socket*/	
		locksocknumber++;
		/* RETURN Socket lock */
		return true; 
	}
	/* RETURN Cant lock socket */
	return false;
}

/* MODEL_FUNC_DEF Unlock socket */
void ldv_unlock_sock(void)
{
	/* ASSERT Socked must be locked before unlocking */
	ldv_assert("linux:sock::double release", locksocknumber > 0);
	/* CHANGE_STATE Unlock socked*/
	locksocknumber--;
}

/* MODEL_FUNC_DEF check on exit */
void ldv_check_final_state(void)
{
	/* ASSERT lock_sock number */
	ldv_assert("linux:sock::all locked sockets must be released", locksocknumber == 0);
}
