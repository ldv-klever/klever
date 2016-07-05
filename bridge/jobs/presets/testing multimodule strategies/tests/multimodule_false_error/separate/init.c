#include <linux/module.h>
#include <linux/mutex.h>

extern int export_with_error(void);

static DEFINE_MUTEX(mutex);

static int __init init(void)
{
	int c = export_with_error();
	if(c != 0) {
	  mutex_lock(&mutex);
	  mutex_lock(&mutex);
	}
	return 0;
}

module_init(init);
