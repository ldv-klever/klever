#include <linux/module.h>
#include <linux/mutex.h>

static DEFINE_MUTEX(mutex);

void bad_export(void) {
}

static int __init binit1(void)
{
	return 0;
}

module_init(binit1);
EXPORT_SYMBOL(bad_export);