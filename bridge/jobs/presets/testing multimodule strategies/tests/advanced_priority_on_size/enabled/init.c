#include <linux/module.h>
#include <linux/mutex.h>

static DEFINE_MUTEX(mutex);

static int __init init1(void)
{
  return 0;
}

void export_err(void)
{
  mutex_lock(&mutex);
  mutex_lock(&mutex);
}

EXPORT_SYMBOL(export_err);
module_init(init1);