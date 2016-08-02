#include <linux/module.h>
#include <linux/mutex.h>

extern void bad_export(void);

int __init ex1_init(void) {
  bad_export();
  return 0;
}

module_init(ex1_init);