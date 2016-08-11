#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/usb.h>
#include <linux/vmalloc.h>


static struct my_struct
{
	const char *name;
	unsigned int *irq;
};

static void memory_allocation_nonatomic(void)
{
	int size;
	void *mem = vmalloc(size);
}

static int __init my_init(void)
{
	struct usb_device *udev, *udev2;
	int flag = 0;
	if (usb_trylock_device(udev)) {
		if (flag) {
			memory_allocation_nonatomic();
		}
		usb_unlock_device(udev);
	}
	else {
		flag = 1;
	}
	if (usb_trylock_device(udev2)) {
		if (flag) {
			memory_allocation_nonatomic();
		}
		usb_unlock_device(udev2);
	}
	return 0;
}

module_init(my_init);
