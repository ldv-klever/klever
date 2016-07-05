#include <linux/module.h>

extern void export_err(void);

static int __init init2(void)
{
  export_err();
  return 0;
}

module_init(init2)