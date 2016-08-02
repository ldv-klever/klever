#include <linux/module.h>
#include <linux/completion.h>

int __init my_init(void)
{
	struct completion *x;
	struct completion *x2;

	init_completion(x);
	init_completion(x2);
	wait_for_completion(x);

	init_completion(x);
	wait_for_completion(x);

	wait_for_completion(x2);

	return 0;
}

module_init(my_init);
