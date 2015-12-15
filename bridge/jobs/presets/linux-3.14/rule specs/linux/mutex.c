#include <linux/kernel.h>
#include <linux/mutex.h>
#include <linux/errno.h>
#include <verifier/rcv.h>
#include <verifier/set.h>

Set LDV_MUTEXES;

/* MODEL_FUNC_DEF Check that a given mutex was not acquired and acquire it */
void ldv_mutex_acquire(struct mutex *lock)
{
  /* ASSERT Acquired mutex should be unacquired */
  ldv_assert(!ldv_set_contains(LDV_MUTEXES, lock));
  /* CHANGE_STATE Acquire mutex */
  ldv_set_add(LDV_MUTEXES, lock);
}

/* MODEL_FUNC_DEF Check that a given mutex was not acquired and nondeterministically acquire it */
int ldv_mutex_acquire_interruptible_or_killable(struct mutex *lock)
{
  /* ASSERT Acquired mutex should be unacquired */
  ldv_assert(!ldv_set_contains(LDV_MUTEXES, lock));
  /* OTHER Nondeterministically acquire mutex */
  if (ldv_undef_int())
  {
    /* MODEL_FUNC_CALL Acquire mutex  */
    ldv_mutex_acquire(lock);
    /* RETURN Successfully acquired mutex */
    return 0;
  }
  else
  {
    /* RETURN Could not acquire mutex */
    return -EINTR;
  }
}

/* MODEL_FUNC_DEF Say whether a given mutex was acquired */
int ldv_mutex_is_acquired(struct mutex *lock)
{
  /* OTHER Either mutex was acquired in this thread or nondeterministically decide whether it was done in another thread */
  if (ldv_set_contains(LDV_MUTEXES, lock) || ldv_undef_int())
  {
    /* RETURN Mutex was acquired in this or in another thread */
    return 1;
  }
  else
  {
    /* RETURN Mutex was not acquired anywhere */
    return 0;
  }
}

/* MODEL_FUNC_DEF Acquire mutex if it was not acquired before */
int ldv_mutex_try_acquire(struct mutex *lock)
{
  /* OTHER Mutex can be acquired if it was not already acquired */
  if (ldv_mutex_is_acquired(lock))
  {
    /* RETURN Mutex was already acquired */
    return 0;
  }
  else
  {
    /* MODEL_FUNC_CALL Acquire mutex  */
    ldv_mutex_acquire(lock);
    /* RETURN Successfully acquired mutex */
    return 1;
  }
}

/* MODEL_FUNC_DEF Decrease a given counter by one and if it becomes 0 check that a given mutex was not acquired and acquire it */
int ldv_mutex_decrement_and_acquire(atomic_t *cnt, struct mutex *lock)
{
  /* OTHER Decrease counter by one */
  cnt->counter--;

  /* OTHER Mutex can be acquired if counter becomes 0 */
  if (cnt->counter)
  {
    /* RETURN Counter is greater then 0, so mutex was not acquired */
    return 0;
  }
  else
  {
    /* ASSERT Acquired mutex should be unacquired */
    ldv_assert(!ldv_set_contains(LDV_MUTEXES, lock));
    /* MODEL_FUNC_CALL Acquire mutex  */
    ldv_mutex_acquire(lock);
    /* RETURN Successfully acquired mutex */
    return 1;
  }
}

/* MODEL_FUNC_DEF Check that a given mutex was acquired and release it */
void ldv_mutex_release(struct mutex *lock)
{
  /* ASSERT Released mutex should be acquired */
  ldv_assert(ldv_set_contains(LDV_MUTEXES, lock));
  /* CHANGE_STATE Release mutex */
  ldv_set_remove(LDV_MUTEXES, lock);
}

/* MODEL_FUNC_DEF Make all mutexes unacquired at the beginning */
void ldv_initialize(void)
{
  /* CHANGE_STATE No mutex is acquired at the beginning */
  ldv_set_init(LDV_MUTEXES);
}

/* MODEL_FUNC_DEF Check that all mutexes are unacquired at the end */
void ldv_check_final_state(void)
{
  /* ASSERT All acquired mutexes should be released before module unloading */
  ldv_assert(ldv_set_is_empty(LDV_MUTEXES));
}