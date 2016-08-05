#include <linux/module.h>
#include <linux/rcupdate.h>
#include <linux/srcu.h>

int __init my_init(void)
{
	struct srcu_struct *sp;
	int idx;

	rcu_read_lock();
	rcu_read_lock();
	rcu_read_lock_bh();
	rcu_read_unlock_bh();
	rcu_read_unlock();
	rcu_read_unlock();
	rcu_read_lock();
	rcu_read_unlock();
	rcu_read_lock_sched();
	rcu_read_unlock_sched();
	srcu_read_lock(sp);
	srcu_read_unlock(sp, idx);

	rcu_barrier();
	rcu_barrier_bh();
	rcu_barrier_sched();
	synchronize_srcu(sp);

	return 0;
}

module_init(my_init);
