#include <linux/module.h>
#include <linux/dm-dirty-log.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>
 
int flip_a_coin;

static int ldv_ctr(struct dm_dirty_log *log, struct dm_target *ti, unsigned argc, char **argv)
{
    ldv_invoke_callback();
    return 0;
}

static void ldv_dtr(struct dm_dirty_log *log)
{
    ldv_invoke_callback();
}

static struct dm_dirty_log_type ldv_type = {
    .name = "ldv",
    .module = THIS_MODULE,
    .ctr = ldv_ctr,
    .dtr = ldv_dtr
};

static int __init ldv_init(void)
{
    flip_a_coin = ldv_undef_int();
    if (flip_a_coin) {
        ldv_register();
        if (!dm_dirty_log_type_register(&ldv_type)) {
            dm_dirty_log_type_unregister(&ldv_type);
            ldv_deregister();
        }
    }
    return 0;
}

static void __exit ldv_exit(void)
{
    if (flip_a_coin) {
        dm_dirty_log_type_unregister(&ldv_type);
        ldv_deregister();
    }
}

module_init(ldv_init);
module_exit(ldv_exit);
