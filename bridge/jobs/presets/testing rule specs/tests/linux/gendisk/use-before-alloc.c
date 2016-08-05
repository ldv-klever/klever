#include <linux/module.h>
#include <linux/genhd.h>

int __init my_init(void)
{
	int minors;
	struct gendisk *disk;

	add_disk(disk);
	return 0;
}

module_init(my_init);
