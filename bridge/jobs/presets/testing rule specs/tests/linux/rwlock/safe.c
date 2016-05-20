#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/spinlock.h>

static int __init init(void)
{
	rwlock_t *rwlock_1;
	rwlock_t *rwlock_2;
	rwlock_t *rwlock_3;
	rwlock_t *rwlock_4;

	unsigned long flags;

	write_lock(rwlock_1);
	write_unlock(rwlock_1);

	read_lock(rwlock_1);
	read_lock_irqsave(rwlock_1, flags);

	write_lock_irq(rwlock_2);
	write_unlock_irq(rwlock_2);

	read_lock_irq(rwlock_2);
	read_lock_bh(rwlock_3);

	write_lock_bh(rwlock_2);
	write_unlock_bh(rwlock_2);

	read_unlock_bh(rwlock_3);
	read_unlock_irq(rwlock_2);
	read_unlock_irqrestore(rwlock_1, flags);
	read_unlock(rwlock_1);

	write_lock_irqsave(rwlock_3, flags);
	write_unlock_irqrestore(rwlock_3, flags);

	if (read_trylock(rwlock_1))
	{
		if (write_trylock(rwlock_1))
		{
			write_unlock(rwlock_1);
		}
		read_unlock(rwlock_1);
	}

	return 0;
}

module_init(init);
