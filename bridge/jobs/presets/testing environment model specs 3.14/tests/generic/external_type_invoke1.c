#include <linux/module.h>
#include <verifier/nondet.h>
#include <linux/emg/test_model.h>

extern int wrapper_register(void);
extern void wrapper_deregister(void);

int __init ldv_init(void)
{
	return wrapper_register();
}

void __exit ldv_exit(void)
{
	wrapper_deregister();
}

module_init(ldv_init);
module_exit(ldv_exit);
