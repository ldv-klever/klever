#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/spinlock.h>

static int __init my_init(void)
{
	spinlock_t *lock;

	spin_lock(lock);
	spin_lock(lock);
	spin_unlock(lock);
	spin_unlock(lock);

	return 0;
}

module_init(my_init);
