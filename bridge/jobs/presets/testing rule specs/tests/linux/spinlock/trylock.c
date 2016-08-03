#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/spinlock.h>

static int __init my_init(void)
{
	spinlock_t *lock_1;
	int is_locked;

	is_locked = spin_trylock(lock_1);
	/* successfully ignore is_locked */
	spin_unlock(lock_1);

	return 0;
}

module_init(my_init);
