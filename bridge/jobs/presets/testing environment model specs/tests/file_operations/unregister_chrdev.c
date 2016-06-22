#include <linux/module.h>
#include <linux/fs.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

unsigned int major;

static int ldv_open(struct inode *inode, struct file *filp)
{
	ldv_invoke_callback();
    return 0;
}

static int ldv_release(struct inode *inode, struct file *filp)
{
	ldv_invoke_callback();
    return 0;
}

static struct file_operations ldv_fops = {
	.open		= ldv_open,
	.release	= ldv_release,
	.owner		= THIS_MODULE,
};

static int __init ldv_init(void)
{
    int flip_a_coin;

	flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        if (!register_chrdev(major, "ldv", &ldv_fops)) {
            unregister_chrdev(major, "ldv");
            ldv_deregister();
        }
    }
    return 0;
}

static void __exit ldv_exit(void)
{
	/* pass */
}

module_init(ldv_init);
module_exit(ldv_exit);