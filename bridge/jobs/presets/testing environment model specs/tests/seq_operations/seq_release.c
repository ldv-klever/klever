#include <linux/module.h>
#include <linux/seq_file.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

struct file *file;
struct inode *inode;

static void *ldv_start(struct seq_file *file, loff_t *pos)
{
	ldv_invoke_callback();
    return 0;
}

static void ldv_stop(struct seq_file *file, void *iter_ptr)
{
	ldv_invoke_callback();
}

static const struct seq_operations ldv_ops = {
	.start = ldv_start,
	.stop  = ldv_stop,
};

static int __init ldv_init(void)
{
	int flip_a_coin;

	flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        if (!seq_open(file, &ldv_ops)) {
            seq_release(inode, file);
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
