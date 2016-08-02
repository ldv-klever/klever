#include <linux/module.h>
#include <linux/sysfs.h>

int __init my_init(void)
{
	const struct attribute_group *grp;
	struct kobject *kobj;

	if(!sysfs_create_group(kobj, grp))
		sysfs_remove_group(kobj, grp);

	return 0;
}

module_init(my_init);
