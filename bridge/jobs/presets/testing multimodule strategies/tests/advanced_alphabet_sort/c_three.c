#include <linux/module.h>
#include <linux/mutex.h>

static DEFINE_MUTEX(mutex);

void bad_export(void) {
}

static int __init cinit1(void)
{
	return 0;
}

module_init(cinit1);
EXPORT_SYMBOL(bad_export);