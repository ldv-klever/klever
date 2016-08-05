#include <linux/module.h>
#include <linux/rcupdate.h>
#include <linux/srcu.h>

int __init my_init(void)
{
	struct srcu_struct *sp;
	srcu_read_lock(sp);
	return 0;
}

module_init(my_init);
