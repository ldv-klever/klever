#include <linux/module.h>

int __init ex2_init(void) {
  return 0;
}

module_init(ex2_init);