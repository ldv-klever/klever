#include <linux/module.h>
#include <linux/mutex.h>

static DEFINE_MUTEX(mutex);

int __init main_init(void) {
  return 0;
}

void bad_export(void) {
  mutex_lock(&mutex);
  mutex_lock(&mutex);
}

EXPORT_SYMBOL(bad_export);
module_init(main_init);