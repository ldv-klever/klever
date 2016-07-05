#include <linux/module.h>
#include <linux/mutex.h>

static DEFINE_MUTEX(mutex);

void bad_export(void) {
  mutex_lock(&mutex);
  mutex_lock(&mutex);
}

static int __init ainit1(void)
{
	return 0;
}

module_init(ainit1);
EXPORT_SYMBOL(bad_export);