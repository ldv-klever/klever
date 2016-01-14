#include <linux/kernel.h>
#include <linux/spinlock.h>

#include <verifier/rcv.h>

/* CHANGE_STATE Read lock state = free*/
int ldv_rlock = 1;
/* CHANGE_STATE Write lock state = free*/
int ldv_wlock = 1;

/* MODEL_FUNC_DEF Acquires the read lock*/
void ldv_read_lock_irqsave(rwlock_t *lock) {
	/* ASSERT Write lock should be in a free state*/
	ldv_assert(ldv_wlock == 1);
	/* CHANGE_STATE Goto locked state*/
	ldv_rlock += 1;
}

/* MODEL_FUNC_DEF Releases the read lock and checks that read lock was acquired before*/
void ldv_read_unlock_irqrestore(rwlock_t *lock) {
	/* ASSERT Lock should be in a locked state*/
	ldv_assert(ldv_rlock > 1);
	/* CHANGE_STATE Goto free state*/
	ldv_rlock -= 1;
}

/* MODEL_FUNC_DEF Acquires the write lock and checks for double write lock*/
void ldv_write_lock_irqsave(rwlock_t *lock) {
	/* ASSERT Write lock should be in a free state*/
	ldv_assert(ldv_wlock == 1);
	/* CHANGE_STATE Goto locked state*/
	ldv_wlock = 2;
}

/* MODEL_FUNC_DEF Releases the write lock and checks that write lock was acquired before*/
void ldv_write_unlock_irqrestore(rwlock_t *lock) {
	/* ASSERT Lock should be in a locked state*/
	ldv_assert(ldv_wlock != 1);
	/* CHANGE_STATE Goto free state*/
	ldv_wlock = 1;
}

/* MODEL_FUNC_DEF Acquires the read lock*/
void ldv_read_lock(rwlock_t *lock) {
	/* ASSERT Write lock should be in a free state*/
	ldv_assert(ldv_wlock == 1);
	/* CHANGE_STATE Goto locked state*/
	ldv_rlock += 1;
}

/* MODEL_FUNC_DEF Releases the read lock and checks that read lock was acquired before*/
void ldv_read_unlock(rwlock_t *lock) {
	/* ASSERT Read lock should be in a locked state*/
	ldv_assert(ldv_rlock > 1);
	/* CHANGE_STATE Goto free state*/
	ldv_rlock -= 1;
}

/* MODEL_FUNC_DEF Acquires the write lock and checks for double write lock*/
void ldv_write_lock(rwlock_t *lock) {
	/* ASSERT Write lock should be in a free state*/
	ldv_assert(ldv_wlock == 1);
	/* CHANGE_STATE Goto locked state*/
	ldv_wlock = 2;
}

/* MODEL_FUNC_DEF Releases the write lock and checks that write lock was acquired before*/
void ldv_write_unlock(rwlock_t *lock) {
	/* ASSERT Write lock should be in a locked state*/
	ldv_assert(ldv_wlock != 1);
	/* CHANGE_STATE Goto free state*/
	ldv_wlock = 1;
}

/* MODEL_FUNC_DEF Tries to acquire the read lock and returns one if successful*/
int ldv_read_trylock(rwlock_t *lock) {
	/* OTHER Construct the nondetermined result*/
	if(ldv_wlock == 1 && ldv_undef_int()) {
		/* CHANGE_STATE Goto locked state*/
		ldv_rlock += 1;
		/* RETURN The read lock is acquired*/
		return 1;
	} else {
		/* RETURN The read lock is not acquired*/
		return 0;
	}
}

/* MODEL_FUNC_DEF Tries to acquire the write lock and returns one if successful*/
int ldv_write_trylock(rwlock_t *lock) {
	/* OTHER Construct the nondetermined result*/
	if(ldv_wlock == 1 && ldv_undef_int()) {
		/* CHANGE_STATE Goto locked state*/
		ldv_wlock = 2;
		/* RETURN The write lock is acquired*/
		return 1;
	} else {
		/* RETURN The write lock is not acquired*/
		return 0;
	}
}

/* MODEL_FUNC_DEF Acquires the read lock*/
void ldv_read_lock_irq(rwlock_t *lock) {
	/* ASSERT Write lock should be in a free state*/
	ldv_assert(ldv_wlock == 1);
	/* CHANGE_STATE Goto locked state*/
	ldv_rlock += 1;
}

/* MODEL_FUNC_DEF Releases the read lock and checks that read lock was acquired before*/
void ldv_read_unlock_irq(rwlock_t *lock) {
	/* ASSERT Read lock should be in a locked state*/
	ldv_assert(ldv_rlock > 1);
	/* CHANGE_STATE Goto free state*/
	ldv_rlock -= 1;
}

/* MODEL_FUNC_DEF Acquires the write lock and checks for double write lock*/
void ldv_write_lock_irq(rwlock_t *lock) {
	/* ASSERT Write lock should be in a free state*/
	ldv_assert(ldv_wlock == 1);
	/* CHANGE_STATE Goto locked state*/
	ldv_wlock = 2;
}

/* MODEL_FUNC_DEF Releases the write lock and checks that write lock was acquired before*/
void ldv_write_unlock_irq(rwlock_t *lock) {
	/* ASSERT Write lock should be in a locked state*/
	ldv_assert(ldv_wlock != 1);
	/* CHANGE_STATE Goto free state*/
	ldv_wlock = 1;
}

/* MODEL_FUNC_DEF Acquires the read lock*/
void ldv_read_lock_bh(rwlock_t *lock) {
	/* ASSERT Write lock should be in a free state*/
	ldv_assert(ldv_wlock == 1);
	/* CHANGE_STATE Goto locked state*/
	ldv_rlock += 1;
}

/* MODEL_FUNC_DEF Releases the read lock and checks that read lock was acquired before*/
void ldv_read_unlock_bh(rwlock_t *lock) {
	/* ASSERT Read lock should be in a locked state*/
	ldv_assert(ldv_rlock > 1);
	/* CHANGE_STATE Goto free state*/
	ldv_rlock -= 1;
}

/* MODEL_FUNC_DEF) Acquires the write lock and checks for double write lock*/
void ldv_write_lock_bh(rwlock_t *lock) {
	/* ASSERT Write lock should be in a free state*/
	ldv_assert(ldv_wlock == 1);
	/* CHANGE_STATE Goto locked state*/
	ldv_wlock = 2;
}

/* MODEL_FUNC_DEF Releases the write lock and checks that write lock was acquired before*/
void ldv_write_unlock_bh(rwlock_t *lock) {
	/* ASSERT Write lock should be in a locked state*/
	ldv_assert(ldv_wlock != 1);
	/* CHANGE_STATE Goto free state*/
	ldv_wlock = 1;
}

/* MODEL_FUNC_DEF Checks that all locks were released*/
void ldv_check_final_state(void) {
	/* ASSERT Read lock should be in a free state*/
	ldv_assert(ldv_rlock == 1);
	/* ASSERT Write lock should be in a free state*/
	ldv_assert(ldv_wlock == 1);
}
