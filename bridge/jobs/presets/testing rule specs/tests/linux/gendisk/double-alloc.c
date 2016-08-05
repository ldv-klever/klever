#include <linux/module.h>
#include <linux/genhd.h>

int __init my_init(void)
{
	int minors;
	struct gendisk *disk;

	disk = alloc_disk(minors);
	disk = alloc_disk(minors);

	return 0;
}

module_init(my_init);
