#include <linux/spinlock.h>
#include <linux/ldv/common.h>
#include <verifier/common.h>

/* CHANGE_STATE Read lock is not aquired at the beginning */
int ldv_rlock = 1;
/* CHANGE_STATE Write lock is not aquired at the beginning */
int ldv_wlock = 1;

/* MODEL_FUNC_DEF Check that write lock is not acquired and acquire read lock */
void ldv_read_lock(rwlock_t *lock)
{
	/* ASSERT Write lock should not be aquired */
	ldv_assert(ldv_wlock == 1);
	/* CHANGE_STATE Acquire read lock */
	ldv_rlock += 1;
}

/* MODEL_FUNC_DEF Check that read lock is acquired and release it */
void ldv_read_unlock(rwlock_t *lock)
{
	/* ASSERT Read lock should be acquired */
	ldv_assert(ldv_rlock > 1);
	/* CHANGE_STATE Release read lock */
	ldv_rlock -= 1;
}

/* MODEL_FUNC_DEF Check that write lock is not aquired and acquire it */
void ldv_write_lock(rwlock_t *lock)
{
	/* ASSERT Write lock should not be aquired */
	ldv_assert(ldv_wlock == 1);
	/* CHANGE_STATE Acquire write lock */
	ldv_wlock = 2;
}

/* MODEL_FUNC_DEF Check that write lock is aquired and release it */
void ldv_write_unlock(rwlock_t *lock)
{
	/* ASSERT Write lock should be aquired */
	ldv_assert(ldv_wlock != 1);
	/* CHANGE_STATE Release write lock */
	ldv_wlock = 1;
}

/* MODEL_FUNC_DEF Try to acquire read lock */
int ldv_read_trylock(rwlock_t *lock)
{
	/* OTHER Nondeterministically acquire read lock if write lock is not acquired */
	if (ldv_wlock == 1 && ldv_undef_int())
	{
		/* CHANGE_STATE Acquire read lock */
		ldv_rlock += 1;
		/* RETURN Read lock was acquired */
		return 1;
	}
	else
	{
		/* RETURN Read lock was not acquired */
		return 0;
	}
}

/* MODEL_FUNC_DEF Try to acquire write lock */
int ldv_write_trylock(rwlock_t *lock)
{
	/* OTHER Nondeterministically acquire write lock if it is not acquired */
	if (ldv_wlock == 1 && ldv_undef_int())
	{
		/* CHANGE_STATE Acquire write lock */
		ldv_wlock = 2;
		/* RETURN Write lock was not acquired */
		return 1;
	}
	else 
	{
		/* RETURN Write lock was not acquired */
		return 0;
	}
}

/* MODEL_FUNC_DEF Check that all read/write locks are unacquired at the end */
void ldv_check_final_state(void)
{
	/* ASSERT All acquired read locks should be released before finishing operation */
	ldv_assert(ldv_rlock == 1);
	/* ASSERT All acquired write locks should be released before finishing operation */
	ldv_assert(ldv_wlock == 1);
}
