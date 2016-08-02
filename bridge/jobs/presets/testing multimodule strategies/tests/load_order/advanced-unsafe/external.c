#include <linux/module.h>
#include <linux/mutex.h>

extern void set_i(void);

int __init init2(void) {
  set_i();
  return 0;
}

module_init(init2);