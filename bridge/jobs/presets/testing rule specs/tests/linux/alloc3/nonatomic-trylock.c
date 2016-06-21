#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/usb.h>
#include <linux/vmalloc.h>


static struct my_struct
{
	const char *name;
	unsigned int *irq;
};

static int undef_int(void)
{
	int nondet;
	return nondet;
}

static void memory_allocation_nonatomic(void)
{
	int size, node;
	void *mem;
	if (undef_int()) mem = vmalloc(size);
	if (undef_int()) mem = vzalloc(size);
	if (undef_int()) mem = vmalloc_user(size);
	if (undef_int()) mem = vmalloc_node(size, node);
	if (undef_int()) mem = vzalloc_node(size, node);
	if (undef_int()) mem = vmalloc_exec(size);
	if (undef_int()) mem = vmalloc_32(size);
	if (undef_int()) mem = vmalloc_32_user(size);
}

static int __init my_init(void)
{
	struct usb_device *udev;
	if (usb_trylock_device(udev)) {
		memory_allocation_nonatomic();
		usb_unlock_device(udev);
	}
	return 0;
}

module_init(my_init);
