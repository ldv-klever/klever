#include <linux/module.h>
#include <linux/dm-dirty-log.h>
#include <linux/emg/test_model.h>
#include <verifier/nondet.h>
 
static int ldv_ctr(struct dm_dirty_log *log, struct dm_target *ti, unsigned argc, char **argv)
{
    ldv_invoke_reached();
}

static void ldv_dtr(struct dm_dirty_log *log)
{
    ldv_invoke_reached();
}

static struct dm_dirty_log_type ldv_type = {
    .name = "ldv",
    .module = THIS_MODULE,
    .ctr = ldv_ctr,
    .dtr = ldv_dtr
};

static int __init ldv_init(void)
{
    ldv_register();
    return dm_dirty_log_type_register(&ldv_type);
}

static void __exit ldv_exit(void)
{
    dm_dirty_log_type_unregister(&ldv_type);
    ldv_deregister();
}

module_init(ldv_init);
module_exit(ldv_exit);
