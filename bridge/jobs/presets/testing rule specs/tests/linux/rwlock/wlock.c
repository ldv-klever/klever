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

	return 0;
}

module_init(init);
