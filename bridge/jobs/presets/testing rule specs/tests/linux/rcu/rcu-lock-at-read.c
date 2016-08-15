#include <linux/module.h>
#include <linux/rcupdate.h>
#include <linux/srcu.h>

int __init my_init(void)
{
	rcu_read_lock();
	rcu_barrier();
	rcu_read_unlock();
	return 0;
}

module_init(my_init);
