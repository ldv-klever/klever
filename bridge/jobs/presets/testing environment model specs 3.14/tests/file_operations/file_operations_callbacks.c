#include <linux/module.h>
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

int flip_a_coin;

static int ldv_open(struct inode *inode, struct file *filp)
{
		int res;

    ldv_invoke_callback();
    res = ldv_undef_int();
    if (!res)
        ldv_probe_up();
    return res;
}

static int ldv_release(struct inode *inode, struct file *filp)
{
		int res;

		ldv_release_down();
		ldv_invoke_callback();
    return 0;
}

static struct file_operations ldv_fops = {
	.open		= ldv_open,
	.release	= ldv_release,
	.owner		= THIS_MODULE,
};

static struct miscdevice ldv_misc = {
    .fops = & ldv_fops
};

static int __init ldv_init(void)
{
	flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        misc_register(&ldv_misc);
    }
    return 0;
}

static void __exit ldv_exit(void)
{
	if (flip_a_coin) {
        misc_deregister(&ldv_misc);
        ldv_deregister();
    }
}

module_init(ldv_init);
module_exit(ldv_exit);
