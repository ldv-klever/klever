#include <linux/module.h>

extern void export_err(void);
int __init big_init(void) {
    
    return 0;
}
module_init(big_init)
