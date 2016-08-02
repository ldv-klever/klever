#include <linux/module.h>
#include <linux/rcupdate.h>
#include <linux/srcu.h>

int __init my_init(void)
{

	struct srcu_struct *sp;
	int idx;
	srcu_read_lock(sp);
	synchronize_srcu(sp);
	srcu_read_unlock(sp, idx);
	return 0;
}

module_init(my_init);
