#include <linux/module.h>
#include <linux/completion.h>

int __init my_init(void)
{
	struct completion *x;

	wait_for_completion(x);
	init_completion(x);

	return 0;
}

module_init(my_init);
