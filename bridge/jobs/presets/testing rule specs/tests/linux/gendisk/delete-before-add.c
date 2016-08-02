#include <linux/module.h>
#include <linux/genhd.h>

int __init my_init(void)
{
	int minors;
	struct gendisk *disk;

	disk = alloc_disk(minors);
	if (!disk)
	    return -1;
	del_gendisk(disk);

	return 0;
}

module_init(my_init);
