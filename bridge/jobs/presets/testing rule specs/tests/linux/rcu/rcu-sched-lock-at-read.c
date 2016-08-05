#include <linux/module.h>
#include <linux/rcupdate.h>
#include <linux/srcu.h>

int __init my_init(void)
{
	rcu_read_lock_sched();
	rcu_barrier_sched();
	rcu_read_unlock_sched();
	return 0;
}

module_init(my_init);
