#include <linux/module.h>
#include <linux/seq_file.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>

int flip_a_coin;
struct file *file;
struct inode *inode;

static void *ldv_start(struct seq_file *file, loff_t *pos)
{
	int res;

    ldv_invoke_callback();
    res = ldv_undef_int();
    if (!res)
        ldv_probe_up();
    return res;
}

static void ldv_stop(struct seq_file *file, void *iter_ptr)
{
	ldv_release_down();
    ldv_invoke_callback();
}

static const struct seq_operations ldv_ops = {
	.start = ldv_start,
	.stop  = ldv_stop,
};

static int __init ldv_init(void)
{
	flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        return seq_open(file, &ldv_ops);
    }
    return 0;
}

static void __exit ldv_exit(void)
{
	if (flip_a_coin) {
        seq_release(inode,file);
        ldv_deregister();
    }
}

module_init(ldv_init);
module_exit(ldv_exit);
