#include <linux/module.h>
#include <linux/mutex.h>

static DEFINE_MUTEX(mutex);

static int __init init(void)
{
	mutex_unlock(&mutex);
	return 0;
}

module_init(init);
