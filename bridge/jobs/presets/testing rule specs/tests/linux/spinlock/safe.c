#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/spinlock.h>
#include <linux/atomic.h>

static int __init my_init(void)
{
	spinlock_t *lock_1;
	spinlock_t *lock_2;

	spin_lock(lock_1);
	spin_lock(lock_2);
	spin_unlock(lock_2);
	spin_unlock(lock_1);

	if (spin_trylock(lock_1))
	{
		spin_unlock(lock_1);
	}

	spin_lock(lock_1);
	if (spin_is_locked(lock_1))
	{
		spin_unlock(lock_1);
	}

	spin_lock(lock_1);
	if (!spin_can_lock(lock_1))
	{
		spin_unlock(lock_1);
	}

	atomic_t *atomic;
	if (atomic_dec_and_lock(atomic, lock_1))
	{
		spin_unlock(lock_1);
	}

	return 0;
}

module_init(my_init);
