#include <linux/module.h>
#include <linux/spinlock.h>

static int __init init(void)
{
	rwlock_t *rwlock_1;

	write_trylock(rwlock_1);
	write_unlock(rwlock_1);

	return 0;
}

module_init(init);
