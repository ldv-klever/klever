#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/spinlock.h>

static int __init my_init(void)
{
	spinlock_t *lock;
	int is_locked;

	is_locked = spin_trylock(lock);
	/* successfully ignore is_locked, spin_is_locked may return true */
	if (spin_is_locked(lock)) {
		spin_unlock(lock);
	}

	return 0;
}

module_init(my_init);
