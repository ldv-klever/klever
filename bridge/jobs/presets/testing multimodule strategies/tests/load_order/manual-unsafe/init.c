#include <linux/module.h>
#include <linux/mutex.h>

static int i;

static DEFINE_MUTEX(mutex);

void set_i(void) {
  i = 7;
}

int __init init1(void) {
  i = 5;
  return 0;
}

void __exit exit1(void) {
  if(i != 5) {
    mutex_lock(&mutex);
    mutex_lock(&mutex);
  }
}

module_init(init1);
module_exit(exit1);

EXPORT_SYMBOL(set_i);